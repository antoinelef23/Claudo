# Review CP-2 — panel of 1 — aggregated verdict: WARN (WARN)

## Panelist 1 — claude-opus-4-8 — angle: full review
VERDICT: WARN

I have all the material. Here is the review file.

---

# Review report — CP-2 (final review & merge) · feature `salle-booking`

**Tasks covered:** T2 (EVAL-1), T3 (EVAL-3), T4 (demo CLI) · **Angle:** full review.

## Evals — merge gate
- ✅ **EVAL-1/2/3 green** — `pytest -m eval`: `8 passed, 51 deselected`. The 3 evals from spec.md §7 are collected (marker `eval`, names containing the ID) and pass at 100%.
- ✅ **Core suite** — `pytest tests/booking_core`: `52 passed`.
- ✅ **EVAL-2 fixed seed** — `tests/booking_core/test_eval_2_property.py:11-12` (`SEED=42`, 500 sequences): deterministic, verifies INV-1/INV-2/INV-3 as required.

## Traceability (spec ↔ commits)
- ✅ **T2** `146f70c` → IDs `[EVAL-1, BHV-1, BHV-1a, BHV-1c, BHV-2, BHV-4]` conformant to tasks.md; diff = `tests/booking_evals/test_eval_1_examples.py` (file_touched respected).
- ✅ **T3** `07bd568` → IDs `[EVAL-3, BHV-4, BHV-3, BHV-2b]` conformant; diff = `tests/booking_evals/test_eval_3_availability.py`.
- ⚠️ **T4** `1127366` — message `T4 manual demo CLI [auto] [auto]`: **no spec ID referenced** and duplicated `[auto]` tag (`work/.../tasks.md:154`). Legitimate in substance (T4 `implements: [demo]`, with no real BHV/INV), but the hard rule "every commit references the spec IDs" is not materialized — to be arbitrated by the Owner. Cosmetic, non-blocking.

## Design conformance (ADR)
- ✅ **ADR-1** (half-open, int minutes) — `model.overlaps()` = `a.start < b.end and b.start < a.end` (`src/booking/model.py:27`); allowed adjacency verified by EVAL-1 EX-3 and EVAL-3.
- ✅ **ADR-2** (soft-delete) — `cancel` sets `status="cancelled"` (`store.py:37`); `confirmed()` filters on `confirmed` (`store.py:40-45`); EVAL-3 proves the slot is freed again (BHV-2b).
- ✅ **INV-1 reuse** (CP-1 fix) — `store.book()` does delegate to `model.overlaps()` (`store.py:5,27`), a single definition of the invariant. The CP-1 rejection reason is addressed.
- ✅ **CLI without `now()`** — time as `--start/--end` arguments (`cli.py:19-45`), in-memory store per invocation (ADR-1, NG-1).

## Scope & quality
- ✅ **No scope creep** — T4 adds no business rule; the non-code diffs (`.runs/`, `.approvals/`, `tasks.md`) are orchestration artifacts.
- ✅ **ruff** clean on `src/booking` + tests; no TODO/FIXME/secret.
- ✅ **CLI** — `--help` exit 0; smoke book/availability functional (correct JSON output).
- ⚠️ **CLI demo limit** — since the store is recreated on each invocation (NG-1 assumed), the CLI cannot illustrate a multi-step workflow (overlap rejected / availability with bookings) across two calls: each command starts from an empty store. **Conformant to the spec** (NG-1, T4 "the store lives for the duration of one invocation"), but limits the value of "manual demo". Informational, to be arbitrated.

## Summary
No blocker: the 3 evals (merge gate) are green, the code follows ADR-1/ADR-2, scope is held, the CP-1 fix is integrated. Two minor gaps to arbitrate (T4 commit traceability with no spec ID + duplicated tag; intrinsically limited scope of the CLI under NG-1). CP-2 being `blocking` (merge always human), I escalate these points to the Owner rather than auto-validate.

VERDICT: WARN