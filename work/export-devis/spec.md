---
artifact: spec
feature: export-devis
version: 1.0.0
status: validated
owner: Antoine (simulation confinement)
validated_by: métier simulé — 2026-06-10
---

# Spec — Export du devis

> Simulation du confinement d'échec : OQ-1 est volontairement NON résolue.
> Un implementer conforme DOIT se bloquer sur T2 au lieu de deviner.

## 1. Intent

Le client veut emporter son devis. L'export doit être dans le format contractuel
défini par le métier — qui n'a pas encore tranché (OQ-1).

**KPI cible :** taux de téléchargement du devis (à mesurer)

## 2. Glossary

| Terme métier (FR) | Nom canonique (code) | Définition |
|---|---|---|
| Export | `export` | Restitution téléchargeable du devis dans le format contractuel |

## 3. Invariants

- **INV-1** — L'export MUST contenir la mention « estimation » (cohérence avec devis-pose INV-2).

## 4. Behaviors

### BHV-1 — Export au format contractuel
- **Given** un devis calculé
- **When** le client demande l'export
- **Then** le devis est restitué en **texte brut** (décision OQ-1) : exactement la sortie de
  `format_quote`, encodée UTF-8
- **Edge cases :** BHV-1a — devis sans pose (surface 0) : export valide, ligne Pose à 0.00 EUR

## 5. Examples

### EX-1 — export du devis EX-2 de devis-pose
```yaml
input:
  quote: {products_eur: 2375.00, installation_eur: 900.00, total_eur: 3275.00, is_estimate: true}
expected_output: |
  chaîne UTF-8 contenant « estimation », « 3275.00 », lignes Produits/Pose distinctes
covers: [BHV-1, INV-1]
```

## 6. Non-goals

- **NG-1** — Envoi par e-mail : hors scope.

## 7. Evals — merge gate

| ID | Type | Description | Couvre | Seuil de succès |
|---|---|---|---|---|
| EVAL-1 | deterministic | l'export texte d'EX-1 contient « estimation », « 3275.00 », lignes distinctes | BHV-1, INV-1 | 100 % |

## 8. Open questions

- **OQ-1** — Le format d'export est-il PDF, CSV, ou les deux ? → *(résolue le 2026-06-10 : **texte brut** via `format_quote`, décision sponsor simulée ; intégrée en BHV-1 et EX-1. PDF = phase 2.)*

## 9. Changelog

| Version | Date | Auteur | Changement |
|---|---|---|---|
| 0.9.0 | 2026-06-10 | simulation | Création — OQ-1 ouverte sciemment |
| 1.0.0 | 2026-06-10 | Owner (simulation) | OQ-1 résolue : export texte brut — BHV-1, EX-1, EVAL-1 précisés |
