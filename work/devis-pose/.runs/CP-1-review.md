Review complete. Here is the CP-1 report.

---

# Review report — CP-1 "validated domain modules" (T2, T3)

**Feature:** `work/devis-pose` · **Spec:** 1.0.0 · **Design:** 1.0.0 · **Evals:** 1062 passed (eval), 1 passed (non-eval), 0 failed

## ✅ Conformant

- **Commit ↔ spec traceability**: `8dea049` references [INV-1..3, BHV-1, BHV-1a, BHV-2, BHV-2a, EVAL-1, EVAL-2], `94d4e4c` [BHV-3, EVAL-3], `fd23610` [EVAL-1, EVAL-2] — all IDs exist in spec.md, and every ID of the `implements` sections of T2/T3 is found in the diff. The `[auto]` commits (`591ea3f`, `5f9c05a`) only touch orchestrator bookkeeping (`state.json`, run log), no code.
- **ADR-1 respected**: pure functions without I/O, exact signature `compute_quote(float, float) -> dict`, `round(x, 2)` rounding at the boundaries (`src/devis/calc.py:22-27`), key contract strictly identical to design §5 (`src/devis/calc.py:24-29`, `src/devis/format.py:13-15`). `format.py` does not depend on `calc` as required by the T3 prompt.
- **Behaviors**: BHV-1 installation at €45/m² (`src/devis/calc.py:3,23`); BHV-2a strictly-greater threshold via `>` (`src/devis/calc.py:18`); INV-3 discount on products only (`src/devis/calc.py:18-20`); INV-2 `is_estimate` always `True` (`src/devis/calc.py:28`).
- **Evals conformant to the convention**: `@pytest.mark.eval` marker present, names containing the lowercase ID (`test_eval_1_exemples_exacts`, `test_eval_2_proprietes`, `test_eval_3_format_ex2`), EX-1/2/3 verified to the euro (`tests/devis_calc/test_evals.py:45`), EVAL-3 verifies "estimation", "3275.00" and distinct lines (`tests/devis_format/test_evals.py:21-32`).
- **Scope**: the code diffs only touch the declared `files_touched` of T2/T3. The fix commit `fd23610` (adding `tests/devis_calc/__init__.py`) stays within the T2 scope and its justification appears in the message (pytest module collision).
- **Hygiene**: no secret, no orphan TODO, docstrings tracing the spec IDs.

## ⚠️ Gaps to arbitrate

1. **"ruff clean" unverifiable**: ruff is not in the dev dependencies (`pyproject.toml:9` — `dev = ["pytest"]`) and `make lint` fails (`Failed to spawn: ruff`). The CLAUDE.md convention (ruff for lint/format) is not tooled — a gap inherited from T1, but it makes this checklist point not mechanically verifiable.
2. **Latent E741**: `tests/devis_format/test_evals.py:28-29` uses the variable `l` (ambiguous-variable-name, ruff rule active by default) — `make lint` will fail as soon as ruff is installed.
3. **EVAL-2: "property-based" type not honored in the strict sense**: spec §7 announces property-based on generated inputs; the implementation is a deterministic parameterized grid (`tests/devis_calc/test_evals.py:48-55`, 1058 cases, spec bounds respected). This is conformant to the approved T2 prompt ("grid of generated inputs") and consistent with the stdlib stack (no hypothesis), but the spec ↔ tasks wording gap warrants either an arbitration or a spec amendment.
4. **Untested branch**: clamping negative inputs to 0 (`src/devis/calc.py:15-16`) implements an interpretation of INV-1 ("whatever the inputs") not made explicit by the spec, and the EVAL-2 grid (amounts/surfaces ≥ 0, conformant to the spec bounds) never exercises it. Reasonable behavior but neither specified nor covered.

## ❌ Blockers

None.

---

Evals EVAL-1..3 are green and traceability is complete, but since the checkpoint is `mode: auto`, the four gaps above (one of them an unverifiable checklist point) require a switch to Owner arbitration rather than auto-validation.

VERDICT: WARN