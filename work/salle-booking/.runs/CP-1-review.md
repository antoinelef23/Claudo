# Review CP-1 — panel of 1 — aggregated verdict: PASS (PASS)

## Panelist 1 — claude-opus-4-8 — angle: full review
VERDICT: PASS

All mechanical checks pass. I'm writing the review report.

---

# Review report — CP-1 · domain vertical slice (salle-booking)

**Tasks covered:** T1 — Pure domain `model` + `store` + `availability` (+ EVAL-2)
**Angle:** full review · **Checkpoint mode:** auto

## ✅ Conformant

**Traceability**
- ✅ Both T1 commits reference valid spec IDs — `f2debb2` carries `[INV-1, INV-2, INV-3, BHV-1, BHV-1a/b/c, BHV-2, BHV-2a/b, BHV-3, BHV-3a, BHV-4, EVAL-2]`, exactly the task's `implements:` (`tasks.md:40`).
- ✅ The fix commit `a30e59c` traces the reason for the previous CP-1 rejection: `store.book() delegates INV-1 to model.overlaps() [INV-1, BHV-2…]`.
- ✅ Each BHV/INV of the task is found in a named test: `test_model.py`, `test_store.py`, `test_availability.py` cover INV-2/INV-3/BHV-1..4 by explicit name; EVAL-2 in `test_eval_2_property.py:16`.

**Recovery from rejection (CP-1 cycle audit)**
- ✅ The previous rejection ("reuse `model.overlaps()` instead of reimplementing the overlap inline", `tasks.md:150`) is **effectively fixed**: `store.py:27` calls `overlaps(existing, candidate)` imported from `model` (`store.py:5`). A single definition of the invariant — enforcement and EVAL-2 share `overlaps()`, no more divergence risk.

**Design conformance**
- ✅ ADR-1 (half-open intervals, int minutes): `overlaps` = `a.start < b.end and b.start < a.end` (`model.py:27`), adjacency `end==start` allowed — tested `test_model.py:74`, `test_availability.py:66`.
- ✅ ADR-2 (soft-delete): `cancel` sets `status="cancelled"` (`store.py:37`); `confirmed()` filters on `status=="confirmed"` (`store.py:44`) → cancelled ignored for overlap (`test_store.py:57`) and availability (`test_availability.py:58`).
- ✅ Design §5 contracts respected identically: `book → {"status":"confirmed","id":…}` / `{"rejected":<reason>}`, reasons `invalid_slot|too_long|overlap`; `cancel → {"status":"cancelled"}|{"rejected":"not_found"}`; `availability → list[tuple[int,int]]`.
- ✅ Purity: no `now()`/`datetime`/I/O, time as input, stdlib only (NG-1/NG-2 respected).

**Scope**
- ✅ Diff strictly within scope — `src/booking/` + `tests/booking_core/` + artifacts/`.runs`. No out-of-scope file touched (verified vs merge base `b4f4492`). EVAL-1/EVAL-3/CLI correctly absent (reserved for T2/T3/T4).

**Quality / evals**
- ✅ `pytest tests/booking_core`: **52 passed**. `-m eval`: **1 passed** (EVAL-2, 500 sequences seed=42). T1 `done_when` satisfied.
- ✅ `ruff check src/booking tests/booking_core`: All checks passed.
- ✅ Types annotated, no secret, no orphan TODO. Code `[auto]` — no manual line to justify.

## ⚠️ Observations (non-blocking, out of T1 scope)

- ⚠️ **Form of the `availability` contract**: the function returns `tuple`s (`availability.py:14`, conformant to design §5 `list[tuple[int,int]]`), whereas spec EX-4 (`spec.md:101`) writes the gaps as lists `[[480,540],…]`. Business source = example YAML; the design decides on `tuple`. To be framed in EVAL-1 (T2) so the comparison is explicit — not a T1 defect.
- ⚠️ **Inverted `availability` window unspecified**: `availability(store, room, ws, we)` with `ws ≥ we` returns `[]` silently. BHV-4 assumes a valid window; no invariant covers it. To be noted as a possible blind spot for a future spec, no impact here.

## ❌ Blockers

None.

---

Checkpoint `mode: auto`: EVAL-2 green, reviewer with no blocking gap, previous rejection fixed, clean scope, design respected. The two ⚠️ are points of attention for T2, not gaps on T1.

VERDICT: PASS