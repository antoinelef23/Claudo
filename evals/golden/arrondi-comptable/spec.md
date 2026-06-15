---
artifact: spec
feature: arrondi-comptable (tâche-or)
version: 1.0.0
status: validated
---

# Spec — Arrondi comptable (tâche-or plus dure)

> Sépare la capacité : `round()` natif de Python fait de l'arrondi *bancaire* (demi-pair)
> et trébuche sur les flottants. La comptabilité exige un **demi-supérieur** exact.

## Invariants
- **INV-1** — l'arrondi est un **ROUND_HALF_UP** (demi-supérieur) sur la valeur décimale,
  PAS le `round()` natif de Python. `2.675 → 2.68`, `0.125 → 0.13`, `1.005 → 1.01`.

## Behaviors
- **BHV-1** — `round_half_up(x, ndigits=2)` arrondit `x` à `ndigits` décimales, demi-supérieur.
- **BHV-2** — `compute_ttc(price_ht) = round_half_up(price_ht × 1.20, 2)` (TVA 20 %).

## Contrat
Le module expose `round_half_up(x: float, ndigits: int = 2) -> float` et
`compute_ttc(price_ht: float) -> float`.
Indice : `Decimal(str(x)).quantize(..., rounding=ROUND_HALF_UP)`.

## Examples
- EX-1 : round_half_up(2.675, 2) → 2.68   (round() natif donnerait 2.67)
- EX-2 : round_half_up(0.125, 2) → 0.13   (round() natif : 0.12)
- EX-3 : round_half_up(2.674, 2) → 2.67   (vers le bas)
- EX-4 : compute_ttc(10.0) → 12.00
