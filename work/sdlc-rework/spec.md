---
type: spec
feature: sdlc-rework
version: 1.0.0
status: validated
owner: Antoine (Owner)
validated_by: Owner — 2026-07-21 (plan approved in session, PR review = final checkpoint)
---

# Spec — SDLC rework (whitepaper gap closure)

## 1. Intent

The analysis of the *New SDLC With Vibe Coding* whitepaper (Google/Kaggle, May 2026)
confirmed the lab's architecture on every fundamental (eval gate, harness engineering,
model routing) and surfaced three concrete gaps: **trajectory observability** (evals are
output-only), **run economics** (cost is captured per run but never aggregated), and
**AI-specific supply-chain risk** (hallucinated dependencies are only prompt-checked).
This feature closes them mechanically, in the lab's own style: small standalone guards,
deterministic, wired into the gate.

**Target KPI:** first-pass success rate visible per role and per model; zero new
dependency entering `pyproject.toml` without a human-reviewed allowlist entry.

## 2. Glossary

| Business term | Canonical name (code) | Definition |
|---|---|---|
| First-pass success | `first_pass_rate` | Share of tasks `done` on attempt 1 |
| Trajectory | `trajectory` | Ordered journal events of a task run (`.runs/journal.jsonl`) |
| Static context | `static_context` | Files loaded on EVERY agent call (CLAUDE.md + role `.md` + profile) |
| Dependency allowlist | `dep_allowlist` | The one sanctioned home for third-party package names |

## 3. Invariants

- **INV-1** — The report and both new inspection tools (trajectory, context budget) are
  **read-only**: they never mutate the repo, git state, or the journal.
- **INV-2** — Guards are **deterministic and offline**: same input ⇒ same verdict, no
  network call.
- **INV-3** — Every dependency declared in `pyproject.toml` (including
  `[dependency-groups]`) MUST appear in `lab/engine/dep_allowlist.txt`.
- **INV-4** — Absence of telemetry is not a failure: a feature without
  `.runs/journal.jsonl` yields "no data" and exit 0 (legacy features keep passing).

## 4. Behaviors

### BHV-1 — Run report (`just report [feature]`)
- **Given** one or more `work/**/.runs/journal.jsonl`
- **When** the Owner runs `just report`
- **Then** it prints, per feature and globally: tasks done/failed/blocked, first-pass
  rate, mean attempts, total cost, cost split task-vs-review, per-model attempts & cost.
- **Edge cases:** BHV-1a — `--json` emits the same numbers machine-readable;
  BHV-1b — `verify_fail` / `eval_fail` events are clustered per task id (top offenders).

### BHV-2 — Trajectory guard (`just check-trajectory work/<f>`)
- **Given** a feature's journal and its git history
- **Then** the guard FAILS (rc 1) if:
  - **BHV-2a** — a `task_done` has no prior successful `task_attempt` (forged or
    corrupt journal);
  - **BHV-2b** — an `[auto]` task commit touched files outside the node's
    `files_touched` ∪ `work/<f>/**` (scope drift that slipped past `scoped_commit`).
- **Edge cases:** BHV-2c — retry-loop smell (≥ 3 attempts, or any `task_failed`) is a
  WARN, printed but rc 0.

### BHV-3 — Context budget (`just context-budget`)
- **Given** the registry (`lab/models/registry.toml`) and the static context files
- **Then** it prints the approximate static-token payload per role
  (CLAUDE.md + role `.md` + context profile), and FAILS **iff** a
  `[context] max_static_tokens` is declared in the registry and exceeded.

### BHV-4 — Dependency guard (`just check-deps`, wired into `gate`/`gate-ci`)
- **Given** `pyproject.toml` and `lab/engine/dep_allowlist.txt`
- **Then** any declared dependency whose canonical name is absent from the allowlist
  fails the gate (rc 1), naming the offending package.

### BHV-5 — Vendor-neutral context entry point
- **Given** a coding agent that reads `AGENTS.md` (not `CLAUDE.md`)
- **Then** a root `AGENTS.md` exists and points to `CLAUDE.md` without duplicating any
  rule (single source of truth).

## 5. Examples

### EX-1 — report on a two-task journal
```yaml
input:
  journal:
    - {event: task_attempt, id: T1, attempt: 1, model: m, cost_usd: 0.10, ok: true}
    - {event: task_done, id: T1, attempts: 1}
    - {event: task_attempt, id: T2, attempt: 1, model: m, cost_usd: 0.20, ok: true}
    - {event: eval_fail, id: T2, attempt: 1}
    - {event: task_attempt, id: T2, attempt: 2, model: m, cost_usd: 0.15, ok: true}
    - {event: task_done, id: T2, attempts: 2}
expected_output:
  tasks_done: 2
  first_pass_rate: 0.5
  mean_attempts: 1.5
  cost_usd: 0.45
covers: [BHV-1, BHV-1a, BHV-1b]
```

### EX-2 — forged journal
```yaml
input:
  journal:
    - {event: task_done, id: T3, attempts: 1}   # no task_attempt before it
expected_output: rc 1, message names T3 and BHV-2a
covers: [BHV-2a]
```

### EX-3 — hallucinated dependency
```yaml
input:
  pyproject_dependencies: ["leftpad-utils"]
  allowlist: ["pytest", "ruff"]
expected_output: rc 1, message names leftpad-utils
covers: [BHV-4, INV-3]
```

## 6. Non-goals

- **NG-1** — No PyPI / network existence check: the human verifies the package when
  adding it to the allowlist (determinism, INV-2).
- **NG-2** — No session-transcript parsing: the journal is the only trajectory source.
- **NG-3** — No automatic model re-routing from report numbers: arbitration stays human
  (`lab/models/EVOLUTION.md`).

## 7. Evals — merge gate

| ID | Type | Description | Covers | Success threshold |
|---|---|---|---|---|
| EVAL-1 | deterministic | EX-1 numbers exact via `run_report` `--json` | BHV-1, BHV-1a, BHV-1b, INV-4 | 100% |
| EVAL-2 | deterministic | EX-2 fails rc 1; scope drift (BHV-2b) fails; clean feature passes; ≥3 attempts = WARN rc 0 | BHV-2a, BHV-2b, BHV-2c | 100% |
| EVAL-3 | deterministic | EX-3 fails rc 1; allowlisted pyproject passes | BHV-4, INV-3 | 100% |
| EVAL-4 | deterministic | budget exceeded ⇒ rc 1; no declared budget ⇒ rc 0 with table | BHV-3 | 100% |
| EVAL-5 | deterministic | root `AGENTS.md` exists, references CLAUDE.md, duplicates no hard rule | BHV-5 | 100% |

## 8. Open questions

None — plan approved by the Owner in session (2026-07-21); the final human checkpoint
is the PR review.

## 9. History

| Version | Date | By | Change |
|---|---|---|---|
| 1.0.0 | 2026-07-21 | Owner + agent | Initial contract from the whitepaper gap analysis |
