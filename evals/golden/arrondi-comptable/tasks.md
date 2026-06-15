---
artifact: tasks
feature: arrondi-comptable
status: approved
---

# Tasks — arrondi-comptable (tâche-or)

### T1 — Implémente round_half_up + compute_ttc
- **files_touched :** `compute.py`
- **prompt :** Implémente `round_half_up(x, ndigits=2)` (demi-supérieur, INV-1) et
  `compute_ttc(price_ht)` (BHV-2) dans `compute.py` selon spec.md et ses Examples.
- **done_when :** `compute.py` expose les deux fonctions, conformes aux Examples.
