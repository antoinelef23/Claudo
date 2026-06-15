---
artifact: spec
feature: repartition
version: 1.0.0
status: validated
owner: Antoine (test E2E — orchestrateur durci)
validated_by: métier simulé — 2026-06-15
---

# Spec — Répartition d'un montant en parts entières

> **Le QUOI. Le contrat du métier.** Répartir un montant entier `total` en `parts` parts
> entières aussi égales que possible, sans perdre ni créer de centime. Périmètre **pur et
> déterministe** (aucune I/O, aucun aléa, aucun `now()`) — un même appel donne toujours la
> même répartition.

## 1. Intent

Partager une somme (centimes, points, unités) entre N bénéficiaires sans reste perdu ni
créé : la somme des parts doit égaler le total exact, et les parts doivent être aussi
équilibrées que possible. Une répartition non déterministe ou qui « perd un centime » est un
incident comptable.

**KPI cible :** 0 écart `somme(parts) ≠ total`.

## 2. Glossary

| Terme métier (FR) | Nom canonique (code) | Définition |
|---|---|---|
| Montant | `total` | Entier ≥ 0 à répartir |
| Parts | `parts` | Nombre entier > 0 de bénéficiaires |
| Répartition | `shares` | Liste de `parts` entiers dont la somme vaut `total` |
| Reste | `remainder` | `total % parts` : les unités à distribuer une à une |

## 3. Inputs / Output (contrat d'appel)

Fonction unique : `split(total: int, parts: int) -> list[int]`.
- `total` : entier ≥ 0. `parts` : entier > 0.
- Retour : liste de longueur `parts`, entiers, **somme exacte = `total`**.
- Entrée invalide (`parts <= 0` ou `total < 0`) → lève `ValueError`.

## 4. Invariants

- **INV-1 — Conservation.** `sum(split(total, parts)) == total`, exactement.
- **INV-2 — Équilibre.** `max(shares) - min(shares) <= 1` (parts aussi égales que possible).
- **INV-3 — Déterminisme.** Même `(total, parts)` → même liste. Aucun `now()`, aucun aléa.
- **INV-4 — Longueur.** `len(split(total, parts)) == parts`.

## 5. Behaviors

### BHV-1 — Répartition exacte (sans reste)
- **Given** `total` divisible par `parts`
- **Then** toutes les parts valent `total // parts`.

### BHV-2 — Distribution du reste
- **Given** un reste `r = total % parts > 0`
- **Then** les **`r` premières** parts reçoivent une unité de plus (déterministe), les autres
  reçoivent `total // parts`. Les parts sont retournées en ordre décroissant-ou-égal.

### BHV-3 — Plus de parts que d'unités
- **Given** `total < parts`
- **Then** les `total` premières parts valent 1, les suivantes valent 0 (somme = `total`).
- **Edge case :** **BHV-3a** — `total == 0` : toutes les parts valent 0.

### BHV-4 — Entrée invalide
- **Given** `parts <= 0` ou `total < 0`
- **Then** lève `ValueError` (aucune liste retournée).

## 6. Examples

### EX-1 — division exacte
```yaml
input: { total: 9, parts: 3 }
expected_output: [3, 3, 3]
covers: [BHV-1]
```

### EX-2 — reste distribué aux premières parts
```yaml
input: { total: 10, parts: 3 }
expected_output: [4, 3, 3]
covers: [BHV-2]
```

### EX-3 — reste de 1 sur 2 parts
```yaml
input: { total: 7, parts: 2 }
expected_output: [4, 3]
covers: [BHV-2]
```

### EX-4 — plus de parts que d'unités
```yaml
input: { total: 2, parts: 5 }
expected_output: [1, 1, 0, 0, 0]
covers: [BHV-3]
```

### EX-5 — total nul
```yaml
input: { total: 0, parts: 3 }
expected_output: [0, 0, 0]
covers: [BHV-3a]
```

## 7. Evals — merge gate

*Convention : test pytest `@pytest.mark.eval`, nom contenant l'ID en minuscules.*

| ID | Type | Description | Couvre | Seuil |
|---|---|---|---|---|
| EVAL-1 | deterministic | EX-1 à EX-5 vérifiés exactement | BHV-1, BHV-2, BHV-3, BHV-3a | 100 % |
| EVAL-2 | property-based | 1000 couples `(total, parts)` aléatoires (seed fixe) : INV-1 (somme), INV-2 (équilibre ≤ 1), INV-4 (longueur) tiennent toujours | INV-1, INV-2, INV-4 | 100 % |
| EVAL-3 | deterministic | entrées invalides (`parts<=0`, `total<0`) lèvent `ValueError` ; déterminisme : deux appels identiques → liste identique | BHV-4, INV-3 | 100 % |

## 8. Non-goals

- **NG-1** — Persistance / I/O : fonction pure en mémoire.
- **NG-2** — Pondérations (parts inégales voulues) : hors scope, répartition uniforme seule.
- **NG-3** — Nombres à virgule : entiers uniquement (centimes/points).

## 9. Open questions

*(aucune — spec close pour le test E2E)*

## 10. Changelog

| Version | Date | Auteur | Changement |
|---|---|---|---|
| 1.0.0 | 2026-06-15 | métier (simulé E2E) | Création — contrat v1 |
