Revue CP-2 terminée. Voici le rapport.

---

# Rapport de revue — CP-2 (merge) · feature `devis-pose` · tâche T4

## ✅ Conformes

**Traçabilité**
- ✅ Commit `22972dd` référence `[BHV-1, BHV-3]` — exactement les `implements` de T4 dans tasks.md:79.
- ✅ BHV-1 et BHV-3 se retrouvent dans le diff : enchaînement `compute_quote` → `format_quote` (`src/devis/cli.py:28-29`), assertions « estimation » + lignes Produits/Pose (`tests/devis_cli/test_cli.py:11-18`).
- ✅ Commit `220ae3e` `[auto]` ne contient que les métadonnées d'orchestration (approbation CP-1, run log) — pas de code.

**Conformité design**
- ✅ `src/devis/cli.py:14-26` : argparse `--products-eur` / `--surface-m2`, stdlib uniquement, conforme à design.md §1 et §3 (zéro dépendance runtime).
- ✅ Contrat de données respecté : le dict de `compute_quote` (clés des Examples, design.md §5) est consommé tel quel par `format_quote`.

**Scope**
- ✅ Commit T4 ne touche que `src/devis/cli.py` + `tests/devis_cli/` — exactement les `files_touched` de tasks.md:81. Aucun scope creep imputable à l'implementer.

**Qualité / gates**
- ✅ Eval gate : `make -s evals` → **1062 passed** (EVAL-1, EVAL-2, EVAL-3 vertes).
- ✅ Suite complète : `uv run pytest -q` → **1064 passed**, dont le test non-eval T4 sur EX-1 (capsys, conforme au prompt de la tâche).
- ✅ `ruff format --check` : 10 fichiers propres. Aucun TODO/FIXME, aucun secret dans `src/` et `tests/`.

## ⚠️ Écarts à arbitrer

1. **Lint non propre** — `ruff check` remonte 2 × E741 (variable ambiguë `l`) à `tests/devis_format/test_evals.py:28` et `tests/devis_format/test_evals.py:29`. C'est du code T3 (déjà validé à CP-1), pas T4, mais CP-2 couvre le diff de bout en bout et CLAUDE.md exige « ruff propre ».
2. **ruff absent des dépendances dev** — `uv run ruff` échoue (non déclaré dans `pyproject.toml`) ; j'ai dû l'exécuter via `uv run --with ruff`. Le gate lint n'est donc pas reproductible en l'état, ce qui explique que l'écart n°1 soit passé inaperçu.
3. **Worktree non propre pour le merge** — `work/devis-pose/.runs/state.json` est modifié et non commité. À committer (métadonnées d'orchestration) ou à écarter avant le merge.
4. **Note d'information** — `scripts/orchestrate.py` (+7 lignes) figure dans le diff de branche sans appartenir aux `files_touched` d'aucune tâche ; il vient du commit de setup `9b5e0b0` (patch harness, antérieur à T1), pas d'un implementer. Pas un scope creep d'agent, mais l'Owner doit le savoir puisque le diff mergé l'inclut.

## ❌ Bloquants

Aucun.

---

**Synthèse pour l'Owner :** T4 est conforme à la spec, au design et à son périmètre ; tous les gates exécutables sont verts. Les écarts sont périphériques (lint sur un fichier T3, outillage ruff, état de worktree) et relèvent d'un arbitrage avant merge — CP-2 étant `mode: blocking`, la décision vous revient de toute façon.

VERDICT: WARN
