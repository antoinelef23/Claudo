---
artifact: spec
feature: webhook-gateway
version: 1.1.1
status: validated
owner: Owner (lab)
---

<!-- Amendement 1.1.0 (2026-06-16) — suite à la revue sécurité CP-2 (security-reviewer, VETO) :
     fermeture de F-1 (IDOR lecture non authentifiée → INV-7 + BHV-6), F-2 (signature non-ASCII
     → 500 au lieu de 401 → BHV-2 précisé), F-3 (corps non borné, DoS pré-auth → BHV-8).
     Amendement 1.1.1 (2026-06-16) — endpoint de santé /healthz → /health : /healthz est réservé/
     intercepté par le Google Front End sur Cloud Run (404 avant le conteneur, constaté en live). -->


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
- **INV-7 — Lecture authentifiée** *(amendement 1.1.0)* : la relecture d'un événement (`GET /events/{id}`) exige un jeton de lecture valide (`X-Read-Token`) ; sans jeton valide → **401**, aucun payload renvoyé. Ferme l'IDOR F-1 : un tiers non authentifié ne peut pas énumérer/exfiltrer les payloads.

## 3. Comportements (Given / When / Then)
- **BHV-1 — Événement valide** : *Given* une requête signée correctement, horodatage frais, `event_id` neuf ; *When* `POST /webhooks/{source}` ; *Then* **202 Accepted**, événement enregistré, corps `{"status":"accepted","event_id":...}`.
- **BHV-2 — Signature invalide** : *Given* une signature fausse/absente/**malformée (y compris non-hexadécimale ou contenant des octets non-ASCII)** ; *When* POST ; *Then* **401** (jamais 500), rien enregistré. *(1.1.0 : précision F-2 — une signature non-ASCII ne doit pas provoquer d'erreur serveur.)*
- **BHV-3 — Horodatage périmé** : *Given* une signature valide mais `timestamp` hors fenêtre ; *When* POST ; *Then* **401**, rien enregistré.
- **BHV-4 — Doublon** : *Given* un `event_id` déjà reçu ; *When* POST à nouveau (signé, frais) ; *Then* **409 Conflict**, magasin inchangé, corps `{"status":"duplicate","event_id":...}`.
- **BHV-5 — Santé** : *When* `GET /health` ; *Then* **200** `{"status":"ok"}`.
- **BHV-6 — Relecture authentifiée** *(amendé 1.1.0)* : *Given* un `X-Read-Token` **valide** ; *When* `GET /events/{event_id}` ; *Then* **200** + payload si connu, **404** sinon. *Given* un token absent/invalide ; *Then* **401**, aucun payload (INV-7).
- **BHV-7 — Corps malformé** : *Given* un JSON invalide ou des champs requis manquants ; *When* POST ; *Then* **400**, rien enregistré.
- **BHV-8 — Corps trop volumineux** *(amendement 1.1.0)* : *Given* un corps dépassant `MAX_BODY = 1 MiB` ; *When* POST ; *Then* **413**, corps non lu intégralement / non traité, rien enregistré (mitige le DoS pré-auth F-3).

## 4. Hors-périmètre (NG)
- **NG-1** : pas de persistance durable dans cette version (magasin en mémoire derrière une interface — un adaptateur Firestore viendra plus tard, sans changer le cœur).
- **NG-2** : pas de file d'attente / retraitement asynchrone ; le traitement métier aval est simulé par l'enregistrement.
- **NG-3** : pas de multi-tenant ; une seule clé de signature par `source` (table statique injectée).

## 5. Entrées / sorties
- **Requête** : `POST /webhooks/{source}` — en-têtes `X-Signature: sha256=<hex>`, `X-Timestamp: <unix_seconds>` ; corps JSON `{"event_id": str, "type": str, "data": object}`.
- **Signature** : `HMAC_SHA256(key_for(source), f"{timestamp}.{raw_body}")` en hexadécimal.
- **Lecture** *(1.1.0)* : `GET /events/{event_id}` — en-tête `X-Read-Token: <token>` (jeton de lecture configuré, injecté). Sans jeton valide → 401 (INV-7).
- **Limite** *(1.1.0)* : `MAX_BODY = 1 MiB` ; au-delà → 413 (BHV-8).
- **Réponses** : 202 / 400 / 401 / 409 / 413 (POST) ; 200 / 401 / 404 (GET) ; 200 (health).

## 6. Exemples (golds — alimentent EVAL-1)
Clé de test `source=acme` → `secret = b"acme-test-key"`. `now = 1_700_000_000`. Fenêtre 300 s. Jeton de lecture `read_token = "read-test-token"` *(1.1.0)*.

| # | Cas | timestamp | event_id | signature | Attendu |
|---|-----|-----------|----------|-----------|---------|
| EX-1 | valide neuf | 1_700_000_000 | evt-1 | correcte | 202, store={evt-1} |
| EX-2 | signature fausse | 1_700_000_000 | evt-2 | `sha256=deadbeef` | 401, store inchangé |
| EX-3 | périmé | 1_699_999_000 (−1000 s) | evt-3 | correcte | 401, store inchangé |
| EX-4 | doublon de EX-1 | 1_700_000_000 | evt-1 | correcte | 409, store inchangé |
| EX-5 | relecture **avec** `X-Read-Token: read-test-token` | — | `GET /events/evt-1` | — | 200 + payload |
| EX-6 | relecture **sans** jeton valide *(1.1.0)* | — | `GET /events/evt-1` | — | 401, aucun payload |

## 7. Evals (merge gate — `make evals`, `pytest -m eval`)
- **EVAL-1** — *examples* : rejoue EX-1..EX-5 via le client de test FastAPI (en process, pas de réseau), vérifie code HTTP **et** état du magasin. Horloge injectée à `now`.
- **EVAL-2** — *property idempotence* : pour `N=500` séquences aléatoires (seed=42) de livraisons d'un même `event_id` mêlées à des `event_id` neufs, le magasin contient exactement l'ensemble des ids distincts et chaque doublon renvoie 409. Vérifie INV-4.
- **EVAL-3** — *property sécurité* : (a) toute signature falsifiée (mutation d'un octet) → 401 (INV-1) ; (b) la frontière de la fenêtre est exacte : `±MAX_SKEW` accepté, `±(MAX_SKEW+1)` rejeté (INV-3) ; (c) la comparaison de signature passe par `hmac.compare_digest` (INV-2 — vérifié par inspection/auto-test du helper) ; **(d)** *(1.1.0)* une signature **non-ASCII / non-hexadécimale** → **401** (jamais 500) (BHV-2/F-2) ; **(e)** *(1.1.0)* `GET /events/{id}` **sans** `X-Read-Token` valide → **401**, aucun payload (INV-7/F-1) ; **(f)** *(1.1.0)* un corps `> MAX_BODY` → **413** (BHV-8/F-3).

## 8. Questions ouvertes (OQ)
*(aucune à ce stade — toute ambiguïté découverte en implémentation s'ajoute ici et stoppe la tâche)*
