---
artifact: design
feature: remise-paliers
version: 1.0.0
status: validated
spec: ./spec.md          # version : 1.0.0
---

# Design — remise-paliers (tâche-or)

Fonction pure, stdlib. Attention aux bornes : `≤` en haut de palier, `>` pour passer au suivant.
Clamp des entrées négatives à 0 avant tout calcul (INV-1).
