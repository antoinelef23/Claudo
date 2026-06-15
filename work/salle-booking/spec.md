---
artifact: spec
feature: salle-booking
version: 1.0.0
status: validated
owner: Antoine (test E2E)
validated_by: métier simulé — 2026-06-15
---

# Spec — Réservation de salles

> **Le QUOI. Le contrat du métier.** Gestionnaire de réservations de salles de réunion :
> réserver un créneau, refuser les chevauchements, annuler, calculer les disponibilités.
> Périmètre **pur et déterministe** (en mémoire, pas d'I/O, le temps est une donnée d'entrée,
> jamais `now()`) — pour qu'il soit testable de bout en bout.

## 1. Intent

Les collaborateurs perdent du temps à coordonner les salles par e-mail et se retrouvent
en double-booking. Cette feature fournit le cœur métier qui garantit qu'une salle n'est
jamais réservée deux fois, et expose les créneaux libres.

**KPI cible :** taux de double-booking 0 % (vs incidents réguliers aujourd'hui).

## 2. Glossary

| Terme métier (FR) | Nom canonique (code) | Définition |
|---|---|---|
| Réservation | `booking` | Occupation d'une salle sur un créneau, avec un statut |
| Salle | `room_id` | Identifiant de salle (chaîne) |
| Créneau | `slot` | Intervalle `[start, end)` en **minutes depuis minuit** (0 à 1440) |
| Chevauchement | `overlap` | Deux créneaux de la même salle dont les intervalles s'intersectent |
| Disponibilité | `availability` | Trous libres d'une salle dans une fenêtre donnée |

## 3. Invariants

- **INV-1** — Deux réservations `confirmed` de la MÊME salle ne se chevauchent JAMAIS.
- **INV-2** — Toute réservation respecte `0 ≤ start < end ≤ 1440`.
- **INV-3** — La durée d'une réservation MUST être ≤ 240 minutes (`end - start ≤ 240`).

## 4. Behaviors

### BHV-1 — Réserver un créneau libre
- **Given** une salle sans réservation chevauchante sur `[start, end)`
- **When** on réserve `(room_id, start, end, holder)`
- **Then** une réservation est créée avec un `id` unique et `status = "confirmed"`
- **Edge cases :**
  - **BHV-1a** — créneaux **adjacents** (`fin de A == début de B`, même salle) : autorisé (pas de chevauchement, `[start, end)` est demi-ouvert).
  - **BHV-1b** — `start >= end` ou hors `[0, 1440]` : rejet, raison `invalid_slot` (INV-2).
  - **BHV-1c** — durée > 240 : rejet, raison `too_long` (INV-3).

### BHV-2 — Refuser un chevauchement
- **Given** une réservation `confirmed` existante sur la salle qui intersecte `[start, end)`
- **When** on tente de réserver le même créneau (même salle)
- **Then** rejet, raison `overlap`, aucune réservation créée
- **Edge cases :**
  - **BHV-2a** — chevauchement sur une AUTRE salle : autorisé.
  - **BHV-2b** — chevauchement avec une réservation `cancelled` : autorisé (l'annulée ne compte pas).

### BHV-3 — Annuler une réservation
- **Given** une réservation `confirmed` d'`id` donné
- **When** on l'annule
- **Then** son `status` passe à `"cancelled"` et son créneau redevient réservable (BHV-2b)
- **Edge cases :** **BHV-3a** — annuler un `id` inexistant : rejet, raison `not_found`.

### BHV-4 — Calculer les disponibilités
- **Given** une salle et une fenêtre `[window_start, window_end)`
- **When** on demande `availability(room_id, window_start, window_end)`
- **Then** retourne la liste des trous libres `(start, end)` dans la fenêtre, **triés par start**,
  en excluant les réservations `confirmed` et en fusionnant les trous adjacents.

## 5. Examples

### EX-1 — réservation nominale
```yaml
input: { op: book, room_id: "A", start: 540, end: 600, holder: "alice" }   # 09:00–10:00
expected_output: { status: "confirmed" }
covers: [BHV-1]
```

### EX-2 — chevauchement refusé
```yaml
given: [{ room_id: "A", start: 540, end: 600 }]
input: { op: book, room_id: "A", start: 570, end: 630 }   # 09:30–10:30 chevauche
expected_output: { rejected: "overlap" }
covers: [BHV-2]
```

### EX-3 — créneaux adjacents autorisés
```yaml
given: [{ room_id: "A", start: 540, end: 600 }]
input: { op: book, room_id: "A", start: 600, end: 660 }   # 10:00–11:00 adjacent
expected_output: { status: "confirmed" }
covers: [BHV-1a]
```

### EX-4 — disponibilités
```yaml
given: [{ room_id: "A", start: 540, end: 600 }, { room_id: "A", start: 660, end: 720 }]
input: { op: availability, room_id: "A", window_start: 480, window_end: 780 }  # 08:00–13:00
expected_output: { gaps: [[480, 540], [600, 660], [720, 780]] }
covers: [BHV-4]
```

### EX-5 — durée trop longue refusée
```yaml
input: { op: book, room_id: "B", start: 540, end: 800 }   # 260 min > 240
expected_output: { rejected: "too_long" }
covers: [BHV-1c]
```

## 6. Non-goals

- **NG-1** — Persistance (base de données) : hors scope, le store est en mémoire.
- **NG-2** — Fuseaux horaires / dates calendaires : on raisonne en minutes depuis minuit sur une journée.
- **NG-3** — Réservations récurrentes : hors scope.

## 7. Evals — merge gate

*Convention : test pytest `@pytest.mark.eval`, nom contenant l'ID en minuscules.*

| ID | Type | Description | Couvre | Seuil |
|---|---|---|---|---|
| EVAL-1 | deterministic | EX-1 à EX-5 vérifiés exactement | BHV-1, BHV-1a, BHV-1c, BHV-2, BHV-4 | 100 % |
| EVAL-2 | property-based | sur 500 séquences de réservations acceptées (seed fixe), INV-1 tient (aucun chevauchement confirmé) | INV-1, INV-2, INV-3 | 100 % |
| EVAL-3 | deterministic | `availability` fusionne les trous adjacents et exclut les `cancelled` (BHV-2b) | BHV-4, BHV-3 | 100 % |

## 8. Open questions

*(aucune — spec close pour le test E2E)*

## 9. Changelog

| Version | Date | Auteur | Changement |
|---|---|---|---|
| 1.0.0 | 2026-06-15 | métier (simulé E2E) | Création — contrat v1 |
