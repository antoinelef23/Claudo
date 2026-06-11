---
artifact: design
feature: export-devis
version: 1.0.0
status: validated
owner: Antoine (simulation confinement)
validated_by: FDE simulé — 2026-06-10
spec: ./spec.md          # version : 1.0.0
---

# Design — Export du devis

Réutilise le socle devis-pose (ADR-1 : fonctions pures). OQ-1 résolue (spec v1.0.0) :
export **texte brut** — `src/devis/export.py::export_quote` encode la sortie de
`format_quote` en UTF-8. Documentation : `docs/export-notes.md` (historique) et
`docs/export-usage.md` (usage).
