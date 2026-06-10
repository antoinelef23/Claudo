---
artifact: spec
feature: devis-pose
version: 1.0.0
status: validated
owner: Antoine (simulation)
validated_by: métier simulé — 2026-06-10
---

# Spec — Devis de pose salle de bain

> **Le QUOI. Le contrat du métier.** Feature de simulation : calculer et formater le devis
> de pose à partir du montant des produits et de la surface. Périmètre volontairement pur
> (pas d'I/O, pas d'API) pour valider le pipeline orchestré de bout en bout.

## 1. Intent

Le client a composé son panier produits ; il veut une estimation du coût total pose comprise,
en une seconde, sans engagement. Cette feature calcule le devis et le formate pour affichage.

**KPI cible :** taux d'ajout du devis au panier (baseline 0 → mesuré au lab)

## 2. Glossary

| Terme métier (FR) | Nom canonique (code) | Définition |
|---|---|---|
| Devis | `quote` | Estimation chiffrée non contractuelle : produits + pose |
| Pose | `installation` | Prestation d'installation facturée au m² |
| Sous-total produits | `products_subtotal_eur` | Somme des prix produits du panier, en euros |
| Remise volume | `volume_discount` | Réduction appliquée au sous-total produits uniquement |

## 3. Invariants

- **INV-1** — Le total d'un devis MUST être ≥ 0, quelles que soient les entrées.
- **INV-2** — Tout devis MUST porter `is_estimate = true` : un devis n'est JAMAIS contractuel.
- **INV-3** — La remise volume MUST s'appliquer au sous-total produits uniquement, jamais à la pose.

## 4. Behaviors

### BHV-1 — Pose au m²
- **Given** une surface de pose `surface_m2` > 0
- **When** le devis est calculé
- **Then** le coût de pose vaut `surface_m2 × 45.00 €`
- **Edge cases :** BHV-1a — `surface_m2 = 0` : pose = 0 €, devis valide (produits seuls)

### BHV-2 — Remise volume
- **Given** un sous-total produits strictement supérieur à 2000 €
- **When** le devis est calculé
- **Then** une remise de 5 % est appliquée au sous-total produits (pas à la pose — INV-3)
- **Edge cases :** BHV-2a — sous-total = 2000.00 € exactement : PAS de remise (strictement supérieur)

### BHV-3 — Formatage client
- **Given** un devis calculé
- **When** il est formaté pour affichage
- **Then** le texte contient le mot « estimation », le total en euros avec exactement 2 décimales,
  et le détail produits / pose sur des lignes séparées

## 5. Examples

### EX-1 — cas nominal sans remise
```yaml
input:
  products_subtotal_eur: 1500.00
  surface_m2: 10
expected_output:
  products_eur: 1500.00
  installation_eur: 450.00
  total_eur: 1950.00
  is_estimate: true
covers: [BHV-1, BHV-2a-implicite, INV-2]
```

### EX-2 — remise volume, pose intacte
```yaml
input:
  products_subtotal_eur: 2500.00
  surface_m2: 20
expected_output:
  products_eur: 2375.00   # 2500 × 0.95
  installation_eur: 900.00  # 20 × 45, PAS remisée (INV-3)
  total_eur: 3275.00
  is_estimate: true
covers: [BHV-2, INV-3]
```

### EX-3 — surface nulle
```yaml
input:
  products_subtotal_eur: 100.00
  surface_m2: 0
expected_output:
  total_eur: 100.00
covers: [BHV-1a]
```

## 6. Non-goals

- **NG-1** — TVA : hors scope, traitée par le moteur de facturation aval.
- **NG-2** — Devises autres que EUR.

## 7. Evals — merge gate

*Convention : un test pytest marqué `@pytest.mark.eval`, nom contenant l'ID en minuscules.*

| ID | Type | Description | Couvre | Seuil de succès |
|---|---|---|---|---|
| EVAL-1 | deterministic | EX-1, EX-2, EX-3 vérifiés à l'euro près | BHV-1, BHV-2, BHV-1a, BHV-2a, INV-3 | 100 % |
| EVAL-2 | property-based | total ≥ 0 et is_estimate=true sur entrées générées (montants 0→10⁶, surfaces 0→500) | INV-1, INV-2 | 100 % |
| EVAL-3 | deterministic | le format de EX-2 contient « estimation », « 3275.00 », lignes produits/pose distinctes | BHV-3 | 100 % |

## 8. Open questions

*(aucune — spec close pour la simulation)*

## 9. Changelog

| Version | Date | Auteur | Changement |
|---|---|---|---|
| 1.0.0 | 2026-06-10 | simulation | Création |
