---
artifact: tasks
feature: devis-calc
status: approved
---

# Tasks — devis-calc (tâche-or)

### T1 — Implémente compute_quote
- **files_touched :** `compute.py`
- **prompt :** Implémente `compute_quote(products_subtotal_eur, surface_m2) -> dict` dans
  `compute.py` selon spec.md (INV-1, INV-2, BHV-1, BHV-2, contrat de clés, Examples).
- **done_when :** `compute.py` expose `compute_quote` conforme aux Examples.
