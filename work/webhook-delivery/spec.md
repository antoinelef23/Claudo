---
artifact: spec
feature: webhook-delivery
version: 1.0.0
status: validated
owner: Antoine (test E2E — "fake real")
validated_by: métier simulé — 2026-06-15
---

# Spec — Service de livraison de webhooks fiable

> **Le QUOI. Le contrat du métier.** Quand un événement se produit, le système doit le livrer au
> webhook d'un abonné de façon **fiable** : signé, réessayé avec backoff en cas d'échec, livré
> **au plus une fois** en cas de succès, et mis en **lettre morte** après trop d'échecs. C'est un
> composant de production classique (tout SaaS en a un).
>
> **Pourquoi « fake real » :** le système s'intègre à un **service externe** (les endpoints HTTP des
> abonnés). Cette intégration passe par un **transport injectable** : en test on injecte un faux
> transport scénarisé (succès/échecs), en prod un transport HTTP réel. Le cœur reste **déterministe**
> (horloge injectée, transport injecté, aucun `now()`, aucun aléa, aucun réseau réel).

## 1. Intent

Les intégrations partenaires échouent silencieusement quand les webhooks ne sont ni réessayés ni
tracés : événements perdus, doublons facturés, support saturé. Ce service garantit qu'un événement
est livré **exactement une fois en cas de succès**, **réessayé proprement** en cas d'échec transitoire,
et **isolé en lettre morte** (sans bloquer le reste) en cas d'échec persistant — le tout **signé** pour
que l'abonné puisse vérifier l'authenticité.

**KPI cible :** 0 livraison en double sur succès ; 0 événement perdu silencieusement (tout finit
`delivered` ou `dead_letter`, jamais entre les deux).

## 2. Glossary

| Terme métier (FR) | Nom canonique (code) | Définition |
|---|---|---|
| Abonné | `subscription` | Destination d'un webhook : `{id, url, secret, max_attempts}` |
| Événement | `event` | Charge à livrer : `{id, payload}` (payload = chaîne JSON) |
| Livraison | `delivery` | État de l'acheminement d'un `event` vers une `subscription` |
| Tentative | `attempt` | Un appel de transport vers l'URL de l'abonné |
| Backoff | `backoff` | Délai (ms) avant la prochaine tentative, croissant |
| Lettre morte | `dead_letter` | État terminal après `max_attempts` échecs |
| Signature | `signature` | HMAC-SHA256 hex du payload avec le `secret` de l'abonné |
| Transport | `transport` | Dépendance injectable qui effectue l'appel réseau (réel en prod, faux en test) |

## 3. Inputs / Output (contrat d'appel)

- Transport (interface injectée) : `send(url: str, payload: str, signature: str) -> bool`
  (`True` = livré/2xx, `False` = échec). Aucun appel réseau dans le cœur : il passe par cette interface.
- Horloge (injectée) : `clock() -> int` — temps logique en millisecondes, croissant. Jamais `now()`.
- `deliver(store, transport, subscription, event, clock, base_ms, cap_ms) -> Delivery` : pilote les
  tentatives jusqu'à l'état terminal (`delivered` ou `dead_letter`).
- États de `Delivery` : `PENDING`, `DELIVERED`, `DEAD_LETTER` (terminaux : les deux derniers).

## 4. Invariants

- **INV-1 — Au plus une fois (succès).** Une `delivery` arrivée à `DELIVERED` n'entraîne plus jamais
  d'appel de transport, même ré-`enqueue`ée.
- **INV-2 — Tentatives bornées.** Le nombre d'appels de transport pour une `delivery` ne dépasse
  JAMAIS `subscription.max_attempts`.
- **INV-3 — Backoff croissant & capé.** `backoff_ms(n) = min(base_ms * 2^(n-1), cap_ms)`, non
  décroissant en `n` (n = numéro de tentative, à partir de 1).
- **INV-4 — Lettre morte terminale.** Après `max_attempts` échecs, l'état est `DEAD_LETTER` et aucune
  tentative ultérieure n'a lieu.
- **INV-5 — Enqueue idempotent.** `enqueue` deux fois le même `(sub_id, event_id)` produit **une seule**
  `delivery`.
- **INV-6 — Signature déterministe.** `sign(secret, payload)` = HMAC-SHA256 hex ; même entrée → même
  signature ; chaque tentative envoie cette signature.
- **INV-7 — Déterminisme.** Horloge et transport injectés ; aucun `now()`, aucun aléa, aucun réseau réel.

## 5. Behaviors

### BHV-1 — Livraison réussie du premier coup
- **Given** un transport qui répond `True`
- **Then** `delivery.state == DELIVERED`, exactement **1** appel de transport, signé (INV-6).

### BHV-2 — Échec transitoire puis succès
- **Given** un transport qui répond `False` puis `True`, `max_attempts >= 2`
- **Then** 2 appels, `next_at` de la 1re tentative = `now + backoff_ms(1)` (INV-3), état final `DELIVERED`.

### BHV-3 — Échec persistant → lettre morte
- **Given** un transport qui répond toujours `False`
- **Then** exactement `max_attempts` appels (INV-2), puis `state == DEAD_LETTER` (INV-4), `last_error` renseigné.

### BHV-4 — Barème de backoff
- **Then** `backoff_ms(1)=base`, `backoff_ms(2)=2*base`, `backoff_ms(3)=4*base`, … capé à `cap_ms`.
- **Edge case :** **BHV-4a** — `base_ms * 2^(n-1) > cap_ms` → `cap_ms` (capé, pas au-delà).

### BHV-5 — Enqueue idempotent
- **Given** `enqueue(sub, evt)` puis à nouveau `enqueue(sub, evt)`
- **Then** une seule `delivery` en store (INV-5) ; le 2e enqueue renvoie la même.

### BHV-6 — Signature HMAC
- **Then** `sign(secret, payload) == hmac_sha256_hex(secret, payload)` ; vérifiable par l'abonné.

### BHV-7 — Re-livraison d'un événement déjà livré = no-op
- **Given** une `delivery` déjà `DELIVERED`
- **When** on rappelle `deliver(...)` pour le même `(sub, event)`
- **Then** aucun nouvel appel de transport (INV-1), l'état reste `DELIVERED`.

## 6. Examples

> Contexte par défaut : `base_ms=1000`, `cap_ms=60000`, horloge logique partant de `0` puis `+1000` par appel.

### EX-1 — succès immédiat
```yaml
given: { subscription: {id: "s1", url: "https://a/hook", secret: "k", max_attempts: 5}, transport: [true] }
input: { op: deliver, event: {id: "e1", payload: "{}"} }
expected: { state: "DELIVERED", calls: 1 }
covers: [BHV-1]
```

### EX-2 — un échec puis succès
```yaml
given: { subscription: {id: "s1", url: "https://a/hook", secret: "k", max_attempts: 5}, transport: [false, true] }
input: { op: deliver, event: {id: "e2", payload: "{}"} }
expected: { state: "DELIVERED", calls: 2 }
covers: [BHV-2]
```

### EX-3 — lettre morte après max_attempts
```yaml
given: { subscription: {id: "s1", url: "https://a/hook", secret: "k", max_attempts: 3}, transport: [false, false, false] }
input: { op: deliver, event: {id: "e3", payload: "{}"} }
expected: { state: "DEAD_LETTER", calls: 3 }
covers: [BHV-3]
```

### EX-4 — barème de backoff (base 1000, cap 60000)
```yaml
input: { op: backoff_series, n: [1, 2, 3, 7, 20] }
expected: [1000, 2000, 4000, 60000, 60000]   # 2^6*1000=64000 -> capé 60000
covers: [BHV-4, BHV-4a]
```

### EX-5 — enqueue idempotent
```yaml
given: { subscription: {id: "s1", url: "https://a/hook", secret: "k", max_attempts: 5} }
input: { op: enqueue_twice, event: {id: "e5", payload: "{}"} }
expected: { deliveries_in_store: 1 }
covers: [BHV-5]
```

## 7. Evals — merge gate

*Convention : test pytest `@pytest.mark.eval`, nom contenant l'ID en minuscules.*

| ID | Type | Description | Couvre | Seuil |
|---|---|---|---|---|
| EVAL-1 | deterministic | EX-1 à EX-5 vérifiés exactement (état + nb d'appels + backoff + idempotence) | BHV-1..BHV-5 | 100 % |
| EVAL-2 | property-based | 1000 scénarios (séquences d'échecs/succès aléatoires, seed fixe) : INV-1 (≤1 succès, pas d'appel après DELIVERED), INV-2 (appels ≤ max_attempts), INV-4 (DEAD_LETTER terminal) tiennent toujours | INV-1, INV-2, INV-4 | 100 % |
| EVAL-3 | deterministic | backoff croissant+capé (INV-3), signature déterministe (INV-6), re-livraison d'un DELIVERED = no-op (BHV-7), enqueue idempotent (INV-5) | INV-3, INV-5, INV-6, BHV-7 | 100 % |

## 8. Non-goals

- **NG-1** — Transport HTTP réel : hors scope du cœur ; on livre l'**interface** `Transport` + un
  `FakeTransport` de test. Un `HttpTransport` réel est une implémentation future, derrière la même interface.
- **NG-2** — Persistance durable (base de données) : le store est en mémoire (NG-1 du lab).
- **NG-3** — Scheduler/cron temps réel : l'horloge est **logique et injectée** ; pas de `sleep`, pas de threads.
- **NG-4** — Vérification de signature côté abonné : on **produit** la signature ; la vérifier est le job de l'abonné.

## 9. Open questions

*(aucune — spec close pour le test E2E)*

## 10. Changelog

| Version | Date | Auteur | Changement |
|---|---|---|---|
| 1.0.0 | 2026-06-15 | métier (simulé E2E) | Création — contrat v1 du service de livraison de webhooks |
