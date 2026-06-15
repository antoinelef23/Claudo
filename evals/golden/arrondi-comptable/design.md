---
artifact: design
feature: arrondi-comptable
version: 1.0.0
status: validated
spec: ./spec.md          # version : 1.0.0
---

# Design — arrondi-comptable (tâche-or)

`decimal.Decimal` + `ROUND_HALF_UP`. Convertir via `Decimal(str(x))` pour éviter l'erreur
de représentation binaire (`Decimal(2.675)` ≠ `Decimal('2.675')`). Renvoyer un `float`.
