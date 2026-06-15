# Revue CP-2 — panel de 1 — verdict agrégé : WARN (WARN)

## Paneliste 1 — claude-opus-4-8 — angle : revue complète
VERDICT: WARN

J'ai tout le matériel. Voici le dossier de revue.

---

# Rapport de revue — CP-2 (revue finale & merge) · feature `salle-booking`

**Tâches couvertes :** T2 (EVAL-1), T3 (EVAL-3), T4 (CLI démo) · **Angle :** revue complète.

## Evals — merge gate
- ✅ **EVAL-1/2/3 vertes** — `pytest -m eval` : `8 passed, 51 deselected`. Les 3 evals de spec.md §7 sont collectées (marker `eval`, noms contenant l'ID) et passent à 100 %.
- ✅ **Suite cœur** — `pytest tests/booking_core` : `52 passed`.
- ✅ **EVAL-2 seed fixe** — `tests/booking_core/test_eval_2_property.py:11-12` (`SEED=42`, 500 séquences) : déterministe, vérifie INV-1/INV-2/INV-3 comme exigé.

## Traçabilité (spec ↔ commits)
- ✅ **T2** `146f70c` → IDs `[EVAL-1, BHV-1, BHV-1a, BHV-1c, BHV-2, BHV-4]` conformes à tasks.md ; diff = `tests/booking_evals/test_eval_1_examples.py` (file_touched respecté).
- ✅ **T3** `07bd568` → IDs `[EVAL-3, BHV-4, BHV-3, BHV-2b]` conformes ; diff = `tests/booking_evals/test_eval_3_availability.py`.
- ⚠️ **T4** `1127366` — message `T4 CLI de démo manuelle [auto] [auto]` : **aucun ID de spec référencé** et tag `[auto]` dupliqué (`work/.../tasks.md:154`). Légitime au fond (T4 `implements: [demo]`, sans BHV/INV réel), mais la hard-rule « chaque commit référence les IDs de la spec » n'est pas matérialisée — à arbitrer par l'Owner. Cosmétique, non bloquant.

## Conformité design (ADR)
- ✅ **ADR-1** (demi-ouvert, minutes int) — `model.overlaps()` = `a.start < b.end and b.start < a.end` (`src/booking/model.py:27`) ; adjacence autorisée vérifiée par EVAL-1 EX-3 et EVAL-3.
- ✅ **ADR-2** (soft-delete) — `cancel` passe `status="cancelled"` (`store.py:37`) ; `confirmed()` filtre sur `confirmed` (`store.py:40-45`) ; EVAL-3 prouve la re-libération du créneau (BHV-2b).
- ✅ **Réutilisation INV-1** (correctif CP-1) — `store.book()` délègue bien à `model.overlaps()` (`store.py:5,27`), une seule définition de l'invariant. Le motif de rejet CP-1 est traité.
- ✅ **CLI sans `now()`** — temps en arguments `--start/--end` (`cli.py:19-45`), store en mémoire par invocation (ADR-1, NG-1).

## Scope & qualité
- ✅ **Pas de scope creep** — T4 n'ajoute aucune règle métier ; les diffs hors code (`.runs/`, `.approvals/`, `tasks.md`) sont des artefacts d'orchestration.
- ✅ **ruff** propre sur `src/booking` + tests ; aucun TODO/FIXME/secret.
- ✅ **CLI** — `--help` exit 0 ; smoke book/availability fonctionnel (sortie JSON correcte).
- ⚠️ **Limite démo CLI** — le store étant recréé à chaque invocation (NG-1 assumé), la CLI ne peut pas illustrer un workflow multi-étapes (overlap refusé / availability avec réservations) entre deux appels : chaque commande repart d'un store vide. **Conforme à la spec** (NG-1, T4 « le store vit le temps d'une invocation »), mais limite la valeur de « démo manuelle ». Informationnel, à arbitrer.

## Synthèse
Aucun bloquant : les 3 evals (gate de merge) sont vertes, le code suit ADR-1/ADR-2, le scope est tenu, le correctif CP-1 est intégré. Deux écarts mineurs à arbitrer (traçabilité du commit T4 sans ID de spec + tag dupliqué ; portée intrinsèquement limitée de la CLI sous NG-1). CP-2 étant `blocking` (merge toujours humain), je remonte ces points à l'Owner plutôt que d'auto-valider.

VERDICT: WARN