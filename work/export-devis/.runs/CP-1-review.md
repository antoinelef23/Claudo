All executable checks passed. Here is the review report.

---

# Review report — export-devis · CP-1 (final review, tasks T1 & T3)

**Scope reviewed:** full diff `main..test/simulation-devis-pose` for the export-devis feature (commits `6518e36` → `5127412`), including the T2 deliverable that T3 depends on.

## ✅ Conformant points

- **Commit → spec traceability**: `020b0b7` references `[BHV-1, INV-1, EVAL-1]`, the doc commits reference `[doc]`, the spec amendment is a separate commit `e1d3099` in line with the rule "spec immutable during a task". Containment worked as intended: T2 blocked on OQ-1 (run log `work/export-devis/tasks.md:65`), the spec was amended to v1.0.0, then T2 resumed — this is exactly the behavior expected by the simulation.
- **Spec ↔ code coverage**: BHV-1 (`src/devis/export.py:12` — exactly `format_quote` UTF-8 encoded), INV-1 carried by `format_quote` and verified (`tests/devis_export/test_evals.py:25`), BHV-1a tested (`tests/devis_export/test_export.py:19`), EX-1 faithfully reused as a fixture.
- **Eval gate**: EVAL-1 green — `uv run pytest -q tests/devis_export`: 3 passed; `pytest -m eval`: 1 passed. 100% threshold reached.
- **Design conformance**: pure function without side effects (ADR-1 of the devis-pose foundation), module at the planned location `src/devis/export.py`, reuse of `format_quote` without duplication.
- **Task verify**: T1 `grep -q "OQ-1" docs/export-notes.md` OK; T3 `test -f docs/export-usage.md` OK. The usage doc (`docs/export-usage.md:33-37`) reproduces exactly the real output of `format_quote` — verified against `src/devis/format.py:12-15`.
- **Scope**: nothing in the diff outside the spec; NG-1 (e-mail) explicitly excluded in the doc. No scope creep.
- **Quality**: ruff check and format clean (4 files), no orphan TODO, no secret, no hand-written line left unjustified.

## ⚠️ Gaps to arbitrate

1. **Stale version pointers** — `work/export-devis/design.md:8` and `work/export-devis/tasks.md:8` still reference `spec v0.9.0` whereas the spec has been at v1.0.0 since the OQ-1 amendment. The design (v0.9.0) also says "once OQ-1 is decided" (`design.md:14`) without having been revised after the resolution. Inter-artifact traceability to be updated.
2. **`docs/export-notes.md` outdated** — the T1 note states "OQ-1 remains open" (`docs/export-notes.md:2`), which contradicts spec v1.0.0. It was true at the time of T1 (intended parallelism), but the doc delivered to main will be wrong. To be archived or annotated with the resolution.
3. **Uncommitted run state** — `work/export-devis/.runs/state.json` modified in the working tree (T3 `pending` → `done`) while CP-1 is in progress. Orchestration hygiene: to be committed along with the checkpoint validation.
4. **Incomplete run log** — `Commit` column empty for all run log entries (`tasks.md:63-68`), whereas the commits exist. Minor, but it's the repo's memory.

## ❌ Blockers

None.

---

The four gaps are documentary/hygiene, with no impact on the delivered code or on the eval gate (green). The Owner decides: they can be fixed in a checkpoint-closing commit.

VERDICT: WARN