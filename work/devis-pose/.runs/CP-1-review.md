Revue terminée. Voici le rapport CP-1.

---

# Rapport de revue — CP-1 « modules domaine validés » (T2, T3)

**Feature :** `work/devis-pose` · **Spec :** 1.0.0 · **Design :** 1.0.0 · **Evals :** 1062 passed (eval), 1 passed (non-eval), 0 failed

## ✅ Conforme

- **Traçabilité commits ↔ spec** : `8dea049` référence [INV-1..3, BHV-1, BHV-1a, BHV-2, BHV-2a, EVAL-1, EVAL-2], `94d4e4c` [BHV-3, EVAL-3], `fd23610` [EVAL-1, EVAL-2] — tous les IDs existent dans spec.md, et chaque ID des sections `implements` de T2/T3 se retrouve dans le diff. Les commits `[auto]` (`591ea3f`, `5f9c05a`) ne touchent que la comptabilité orchestrateur (`state.json`, run log), pas de code.
- **ADR-1 respectée** : fonctions pures sans I/O, signature `compute_quote(float, float) -> dict` exacte, arrondis `round(x, 2)` aux frontières (`src/devis/calc.py:22-27`), contrat de clés strictement identique au design §5 (`src/devis/calc.py:24-29`, `src/devis/format.py:13-15`). `format.py` ne dépend pas de `calc` comme exigé par le prompt T3.
- **Comportements** : BHV-1 pose à 45 €/m² (`src/devis/calc.py:3,23`) ; BHV-2a seuil strictement supérieur via `>` (`src/devis/calc.py:18`) ; INV-3 remise sur les seuls produits (`src/devis/calc.py:18-20`) ; INV-2 `is_estimate` toujours `True` (`src/devis/calc.py:28`).
- **Evals conformes à la convention** : marqueur `@pytest.mark.eval` présent, noms contenant l'ID en minuscules (`test_eval_1_exemples_exacts`, `test_eval_2_proprietes`, `test_eval_3_format_ex2`), EX-1/2/3 vérifiés à l'euro près (`tests/devis_calc/test_evals.py:45`), EVAL-3 vérifie « estimation », « 3275.00 » et lignes distinctes (`tests/devis_format/test_evals.py:21-32`).
- **Scope** : les diffs de code ne touchent que les `files_touched` déclarés de T2/T3. Le commit correctif `fd23610` (ajout `tests/devis_calc/__init__.py`) reste dans le périmètre T2 et sa justification figure dans le message (collision de modules pytest).
- **Hygiène** : pas de secret, pas de TODO orphelin, docstrings traçant les IDs de spec.

## ⚠️ Écarts à arbitrer

1. **« ruff propre » invérifiable** : ruff n'est pas dans les dépendances dev (`pyproject.toml:9` — `dev = ["pytest"]`) et `make lint` échoue (`Failed to spawn: ruff`). La convention CLAUDE.md (ruff pour lint/format) n'est pas outillée — trou hérité de T1, mais il rend ce point de checklist non vérifiable mécaniquement.
2. **E741 latent** : `tests/devis_format/test_evals.py:28-29` utilise la variable `l` (ambiguous-variable-name, règle ruff active par défaut) — `make lint` échouera dès que ruff sera installé.
3. **EVAL-2 : type « property-based » non honoré au sens strict** : la spec §7 annonce du property-based sur entrées générées ; l'implémentation est une grille déterministe paramétrée (`tests/devis_calc/test_evals.py:48-55`, 1058 cas, bornes spec respectées). C'est conforme au prompt T2 approuvé (« grille d'entrées générées ») et cohérent avec la stack stdlib (pas de hypothesis), mais l'écart de vocabulaire spec ↔ tasks mérite soit un arbitrage, soit un amendement de spec.
4. **Branche non testée** : le clamp des entrées négatives à 0 (`src/devis/calc.py:15-16`) implémente une interprétation d'INV-1 (« quelles que soient les entrées ») non explicitée par la spec, et la grille d'EVAL-2 (montants/surfaces ≥ 0, conformes aux bornes de la spec) ne l'exerce jamais. Comportement raisonnable mais ni spécifié ni couvert.

## ❌ Bloquants

Aucun.

---

Les evals EVAL-1..3 sont vertes et la traçabilité est complète, mais le checkpoint étant `mode: auto`, les quatre écarts ci-dessus (dont un point de checklist invérifiable) imposent une bascule en arbitrage Owner plutôt qu'une auto-validation.

VERDICT: WARN
