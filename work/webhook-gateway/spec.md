---
artifact: spec
feature: webhook-gateway
version: 1.0.0
status: validated
owner: Owner (lab)
---

# Spec — Webhook Gateway (récepteur de webhooks signés)

> **Le QUOI.** Un service HTTP qui reçoit des webhooks entrants d'un partenaire, en vérifie
> l'authenticité (signature HMAC), rejette les rejeux (fenêtre de fraîcheur), et garantit
> l'idempotence (un même événement traité une seule fois). Contrat métier — pas d'implémentation ici.

## 1. Contexte
Des partenaires nous POSTent des événements (paiement, commande…). On doit : (a) prouver que
l'appel vient bien du partenaire, (b) refuser un appel rejoué par un tiers, (c) ne jamais traiter
deux fois le même événement même si le partenaire réémet. Le service est **stateless** côté logique
(le magasin d'événements est injecté) et **déterministe** (horloge injectée).

## 2. Invariants (MUST — toujours vrais)
- **INV-1 — Authenticité** : une requête dont la signature HMAC-SHA256 est absente ou invalide est **rejetée (401)** et **jamais** enregistrée ni traitée.
- **INV-2 — Comparaison constante** : la vérification de signature utilise une comparaison à temps constant (`hmac.compare_digest`), jamais `==`.
- **INV-3 — Anti-rejeu** : une requête dont l'horodatage signé est plus vieux que la fenêtre de fraîcheur (`MAX_SKEW = 300 s`) ou en avance de plus de `MAX_SKEW` est **rejetée (401)**.
- **INV-4 — Idempotence** : pour un `event_id` donné, l'événement est enregistré **au plus une fois** ; une seconde livraison ne crée pas de doublon et n'a aucun effet de bord supplémentaire.
- **INV-5 — Déterminisme** : la logique cœur n'appelle ni horloge système ni réseau ; l'instant courant et le magasin sont **injectés** (testable, rejouable).
- **INV-6 — Pas de fuite** : aucune signature, clé ou payload sensible n'est journalisé ; un échec de signature ne révèle pas pourquoi (pas d'oracle).

## 3. Comportements (Given / When / Then)
- **BHV-1 — Événement valide** : *Given* une requête signée correctement, horodatage frais, `event_id` neuf ; *When* `POST /webhooks/{source}` ; *Then* **202 Accepted**, événement enregistré, corps `{"status":"accepted","event_id":...}`.
- **BHV-2 — Signature invalide** : *Given* une signature fausse/absente ; *When* POST ; *Then* **401**, rien enregistré.
- **BHV-3 — Horodatage périmé** : *Given* une signature valide mais `timestamp` hors fenêtre ; *When* POST ; *Then* **401**, rien enregistré.
- **BHV-4 — Doublon** : *Given* un `event_id` déjà reçu ; *When* POST à nouveau (signé, frais) ; *Then* **409 Conflict**, magasin inchangé, corps `{"status":"duplicate","event_id":...}`.
- **BHV-5 — Santé** : *When* `GET /healthz` ; *Then* **200** `{"status":"ok"}`.
- **BHV-6 — Relecture** : *When* `GET /events/{event_id}` ; *Then* **200** + payload si connu, **404** sinon.
- **BHV-7 — Corps malformé** : *Given* un JSON invalide ou des champs requis manquants ; *When* POST ; *Then* **400**, rien enregistré.

## 4. Hors-périmètre (NG)
- **NG-1** : pas de persistance durable dans cette version (magasin en mémoire derrière une interface — un adaptateur Firestore viendra plus tard, sans changer le cœur).
- **NG-2** : pas de file d'attente / retraitement asynchrone ; le traitement métier aval est simulé par l'enregistrement.
- **NG-3** : pas de multi-tenant ; une seule clé de signature par `source` (table statique injectée).

## 5. Entrées / sorties
- **Requête** : `POST /webhooks/{source}` — en-têtes `X-Signature: sha256=<hex>`, `X-Timestamp: <unix_seconds>` ; corps JSON `{"event_id": str, "type": str, "data": object}`.
- **Signature** : `HMAC_SHA256(key_for(source), f"{timestamp}.{raw_body}")` en hexadécimal.
- **Réponses** : 202 / 400 / 401 / 409 (POST) ; 200 / 404 (GET) ; 200 (healthz).

## 6. Exemples (golds — alimentent EVAL-1)
Clé de test `source=acme` → `secret = b"acme-test-key"`. `now = 1_700_000_000`. Fenêtre 300 s.

| # | Cas | timestamp | event_id | signature | Attendu |
|---|-----|-----------|----------|-----------|---------|
| EX-1 | valide neuf | 1_700_000_000 | evt-1 | correcte | 202, store={evt-1} |
| EX-2 | signature fausse | 1_700_000_000 | evt-2 | `sha256=deadbeef` | 401, store inchangé |
| EX-3 | périmé | 1_699_999_000 (−1000 s) | evt-3 | correcte | 401, store inchangé |
| EX-4 | doublon de EX-1 | 1_700_000_000 | evt-1 | correcte | 409, store inchangé |
| EX-5 | relecture connue | — | `GET /events/evt-1` | — | 200 + payload |

## 7. Evals (merge gate — `make evals`, `pytest -m eval`)
- **EVAL-1** — *examples* : rejoue EX-1..EX-5 via le client de test FastAPI (en process, pas de réseau), vérifie code HTTP **et** état du magasin. Horloge injectée à `now`.
- **EVAL-2** — *property idempotence* : pour `N=500` séquences aléatoires (seed=42) de livraisons d'un même `event_id` mêlées à des `event_id` neufs, le magasin contient exactement l'ensemble des ids distincts et chaque doublon renvoie 409. Vérifie INV-4.
- **EVAL-3** — *property sécurité* : (a) toute signature falsifiée (mutation d'un octet) → 401 (INV-1) ; (b) la frontière de la fenêtre est exacte : `±MAX_SKEW` accepté, `±(MAX_SKEW+1)` rejeté (INV-3) ; (c) la comparaison de signature passe par `hmac.compare_digest` (INV-2 — vérifié par inspection/auto-test du helper).

## 8. Questions ouvertes (OQ)
*(aucune à ce stade — toute ambiguïté découverte en implémentation s'ajoute ici et stoppe la tâche)*
