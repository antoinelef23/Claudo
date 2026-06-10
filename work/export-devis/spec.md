---
artifact: spec
feature: export-devis
version: 0.9.0
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
- **Then** le devis est restitué dans **le format contractuel défini par le métier — voir OQ-1, NON RÉSOLUE**
- **Edge cases :** indéterminés tant qu'OQ-1 est ouverte

## 5. Examples

*(impossibles à écrire tant qu'OQ-1 est ouverte)*

## 6. Non-goals

- **NG-1** — Envoi par e-mail : hors scope.

## 7. Evals — merge gate

| ID | Type | Description | Couvre | Seuil de succès |
|---|---|---|---|---|
| EVAL-1 | deterministic | l'export d'EX-2 (devis-pose) respecte le format contractuel | BHV-1, INV-1 | 100 % |

## 8. Open questions

- **OQ-1** — Le format d'export est-il PDF, CSV, ou les deux ? Décision métier attendue (sponsor). **NON RÉSOLUE.**

## 9. Changelog

| Version | Date | Auteur | Changement |
|---|---|---|---|
| 0.9.0 | 2026-06-10 | simulation | Création — OQ-1 ouverte sciemment |
