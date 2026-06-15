---
artifact: spec
feature: devis-calc (tâche-or)
version: 1.0.0
status: validated
---

# Spec — Calcul de devis (tâche-or du harnais)

> Tâche-or pour le scorecard : le modèle écrit l'implémentation, jugée contre NOS
> evals cachées (`goldeval/`, non fournies au modèle). Périmètre pur, déterministe.

## Invariants
- **INV-1** — le total MUST être ≥ 0 quelles que soient les entrées (entrées négatives ramenées à 0).
- **INV-2** — `is_estimate` MUST toujours valoir `True`.

## Behaviors
- **BHV-1** — pose : `installation_eur = surface_m2 × 45.0`.
- **BHV-2** — remise : si `products_subtotal_eur > 2000`, remise de 5 % sur les produits SEULEMENT.

## Contrat
`compute_quote(products_subtotal_eur: float, surface_m2: float) -> dict` renvoie les clés
`products_eur`, `installation_eur`, `total_eur`, `is_estimate`, arrondies à 2 décimales.

## Examples
- EX-1 : (1500, 10) → products 1500.00, installation 450.00, total 1950.00
- EX-2 : (2500, 20) → products 2375.00, installation 900.00, total 3275.00
- EX-3 : (100, 0)  → total 100.00
