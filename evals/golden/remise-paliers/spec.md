---
artifact: spec
feature: remise-paliers (tâche-or)
version: 1.0.0
status: validated
---

# Spec — Remise par paliers (tâche-or plus dure)

> Sépare la capacité : les **bornes de paliers** et le **clamp** sont faciles à rater.

## Invariants
- **INV-1** — total ≥ 0 ; `products_subtotal_eur` et `surface_m2` négatifs ramenés à 0.
- **INV-3** — la remise s'applique au sous-total PRODUITS uniquement, jamais à la pose.

## Behaviors
- **BHV-1** — `installation_eur = surface_m2 × 45.0`.
- **BHV-2** — remise par paliers sur le sous-total produits (bornes INCLUSIVES en haut) :
  - `products ≤ 1000` → 0 %
  - `1000 < products ≤ 5000` → 5 %
  - `products > 5000` → 10 %

## Contrat
`compute_total(products_subtotal_eur: float, surface_m2: float) -> dict` →
clés `products_eur`, `installation_eur`, `total_eur`, `is_estimate` (arrondi 2 décimales).

## Examples
- EX-1 : (1000, 0) → products 1000.00 (palier 0 %), total 1000.00
- EX-2 : (1000.01, 0) → products 950.01 (palier 5 %)
- EX-3 : (5000, 10) → products 4750.00 (5 %), installation 450.00, total 5200.00
- EX-4 : (5000.01, 0) → products 4500.01 (palier 10 %)
- EX-5 : (-100, -5) → total 0.00 (clamp)
