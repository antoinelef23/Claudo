#!/usr/bin/env python3
"""Background orchestrator for the AI-native lab.

Reads a feature's tasks.md, builds the DAG (depends_on), runs the ready tasks
IN PARALLEL via `claude -p` (headless), passes the eval gate after each task
(max 3 iterations), and handles checkpoints according to their mode:
  - `mode: blocking` (default) — pause + notification, human validation via
        scripts/approve.sh CP-1 <feature_dir>
  - `mode: auto` — auto-validated if and only if evals green AND reviewer PASS;
        otherwise falls back to blocking. The final (merge) checkpoint is ALWAYS blocking.

Autonomy levels:
    --dry-run       show the plan, nothing runs
    --supervised    force all checkpoints to blocking (ignore auto modes)
    (default)       cruise: respect the modes of the plan approved by the Owner
    --validate      plan-lint: check tasks.md and exit (to be run by the planner
                    BEFORE proposing the plan, and by the Owner before approving)

Autonomy guardrails:
  - structured verdict: the implementer ends with STATUS: done|blocked — an agent
    blocked on a spec gap (OQ) never passes for finished
  - anti-empty-gate: a task that implements spec IDs fails if NO eval is
    collected (no eval written = no done, even if `just evals` exits 0)
  - failure containment: a failed/blocked task only blocks its own subtree of
    dependents (skipped); the other branches continue
  - scoped commits: we only stage the task's files_touched + the feature
    directory under lock (never `git add -A`, nor `tests`/`evals` wholesale which
    would suck in the files of other tasks and the goldens — findings H3/H5)

Usage:
    python3 scripts/orchestrate.py work/my-feature --validate
    python3 scripts/orchestrate.py work/my-feature --dry-run
    caffeinate -i python3 scripts/orchestrate.py work/my-feature &   # runs in background

Prerequisites: claude CLI installed and authenticated; tasks.md with status: approved
(frontmatter) — the orchestrator refuses an unvalidated plan (Cognition pattern).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import approvals
from notify import notify
from planlint import validate
from plan import (
    SPEC_ID,
    Node,
    parse_tasks_md,
    paths_overlap,
    skip_dependents,
)
from registry import load_registry, resolve_model
from runner import DEFAULT_ALLOWED_TOOLS, get_runner
from verify import parse_verify

# LAB_ROOT: override for tests (sandbox) — default: the repo root
ROOT = Path(os.environ.get("LAB_ROOT") or Path(__file__).resolve().parent.parent)
REGISTRY = load_registry(
    ROOT
)  # model×role assignment (empty if no models/registry.toml)
MAX_EVAL_RETRIES = 3
MAX_PARALLEL = 3
MAX_CP_REJECTS = 2  # beyond this: the checkpoint goes failed, manual resume
BUDGET_USD = float(os.environ.get("LAB_BUDGET_USD", "0") or 0)  # 0 = no cap
TASK_TIMEOUT_S = int(
    os.environ.get("LAB_TASK_TIMEOUT", "2400")
)  # wall per agent: 40 min
MAX_TURNS = 100
# Bash whitelist so the implementer can run its tests (acceptEdits covers edits,
# not Bash). NOT a security boundary — real confinement is the sandbox runner.
ALLOWED_TOOLS = list(DEFAULT_ALLOWED_TOOLS)
# Execution backend (LAB_RUNNER: claude-cli default | sandbox). The orchestrator
# depends on this interface, not on the `claude` binary.
RUNNER = get_runner()

COMMIT_LOCK = threading.Lock()
LOG_LOCK = threading.Lock()
COST_LOCK = threading.Lock()
COST_TOTAL = {"usd": 0.0}
# fd of the inter-process flock kept open for the whole run (released on process
# exit by the OS). Prevents two orchestrators from racing on the same feature.
_ORCH_LOCK_FD: int | None = None


def acquire_orchestrator_lock(feature: Path) -> None:
    """Exclusive OS flock on .runs/orchestrator.lock — fail-fast if already held (finding H6).

    Two orchestrate.py processes on the same feature would corrupt state.json, the
    git index, the journal and the budget (COST_TOTAL is per-process). threading.Lock
    only protects intra-process. The fd stays open: the OS releases it at process end.
    """
    global _ORCH_LOCK_FD
    lock_path = feature / ".runs" / "orchestrator.lock"
    lock_path.parent.mkdir(exist_ok=True, parents=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # exclusive, non-blocking
    except OSError as e:
        os.close(fd)
        raise OSError(
            f"orchestrator lock already held on {lock_path} — another run is active "
            "on this feature. Wait for it to finish (or delete the .lock if it is stale)."
        ) from e
    _ORCH_LOCK_FD = fd


def atomic_write_json(path: Path, obj: dict) -> None:
    """Write a JSON atomically (tempfile + os.replace) — no truncation
    on SIGKILL mid-write (finding L9)."""
    path.parent.mkdir(exist_ok=True, parents=True)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=str(path.parent), delete=False, suffix=".tmp", encoding="utf-8"
    ) as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        tmp = f.name
    try:
        os.replace(tmp, str(path))
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def eval_covers(spec_id: str, collected: str) -> bool:
    """True if a collected eval carries spec_id, by matching the pytest NODE ID
    (finding M7). We look at the test name AFTER "::" (not the file path),
    and forbid a numeric prefix collision: eval_1 != eval_10,
    and tests/eval_2_helpers.py does not "cover" EVAL-2."""
    slug = spec_id.lower().replace("-", "_")  # EVAL-1 -> eval_1
    pat = re.compile(rf"(?<![a-z0-9]){re.escape(slug)}(?![0-9])")
    for line in collected.splitlines():
        if "::" not in line:
            continue
        node_id = line.rsplit("::", 1)[1]  # test name, not the path
        if pat.search(node_id.lower()):
            return True
    return False


# ---------------------------------------------------------------- execution


def run_log(feature: Path, node: Node, agent: str, result: str) -> None:
    line = f"| {datetime.now():%Y-%m-%d %H:%M} | {node.id} | {agent} | {result} | |\n"
    with LOG_LOCK, (feature / "tasks.md").open("a", encoding="utf-8") as f:
        f.write(line)


def journal(feature: Path, **event) -> None:
    """Run telemetry: one JSON line per event in .runs/journal.jsonl."""
    event["ts"] = datetime.now().isoformat(timespec="seconds")
    path = feature / ".runs" / "journal.jsonl"
    with LOG_LOCK:
        path.parent.mkdir(exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def run_claude(
    prompt: str, resume: str | None = None, model: str | None = None
) -> dict:
    """Headless claude call. Returns {ok, text, session_id, cost_usd, error}.

    Wall-clock wall TASK_TIMEOUT_S: a stuck agent never blocks its wave
    indefinitely. --output-format json output: result text, session_id
    (to resume the SAME session on retry instead of starting over) and
    cost, aggregated into COST_TOTAL for the summary (Twin Track metric).
    model: --model passed as-is (CLI default if None).
    """
    # The approval secret must NEVER be visible to a sub-agent: otherwise
    # it could sign its own checkpoint validation (finding H1).
    child_env = {k: v for k, v in os.environ.items() if k != approvals.ENV_SECRET}
    r = RUNNER.run(
        prompt,
        cwd=ROOT,
        model=model,
        resume=resume,
        allowed_tools=ALLOWED_TOOLS,
        max_turns=MAX_TURNS,
        timeout=TASK_TIMEOUT_S,
        env=child_env,
    )
    with COST_LOCK:
        COST_TOTAL["usd"] += r.cost_usd
    return {
        "ok": r.ok,
        "text": r.text,
        "session_id": r.session_id,
        "cost_usd": r.cost_usd,
        "error": r.error,
    }


def run_evals() -> tuple[bool, str]:
    p = subprocess.run(["just", "evals"], cwd=ROOT, capture_output=True, text=True)
    return p.returncode == 0, (p.stdout + p.stderr)[-3000:]


def evals_collected() -> str:
    """Raw list of collected evals (`pytest --collect-only`).

    Serves the anti-empty-gate (empty = nothing to gate) AND ID coverage:
    the convention "test name containing the lowercased ID" makes each
    EVAL-n in the spec mechanically verifiable.
    LAB_EVALS_COLLECTED_FILE: test seam (content read as-is).
    """
    hook = os.environ.get("LAB_EVALS_COLLECTED_FILE")
    if hook:
        p = Path(hook)
        return p.read_text(encoding="utf-8") if p.exists() else ""
    if not (ROOT / "pyproject.toml").exists():
        return ""
    p = subprocess.run(
        ["uv", "run", "pytest", "-m", "eval", "--collect-only", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return p.stdout


def scoped_commit(node: Node, feature: Path, message: str) -> None:
    """Stage only the task's scope, under lock (parallel waves).

    We NO LONGER stage `tests`/`evals` wholesale (findings H3/H5): by convention,
    files_touched already contains the task's tests/evals paths. Wholesale staging
    used to suck in the files of other tasks in the wave AND the
    `evals/golden/**` oracles — an out-of-scope tampered golden ended up
    auto-committed, corrupting the scorecard ground truth. So we stage node.files +
    the feature directory (spec/design/tasks), then un-stage any undeclared golden.
    """
    with COMMIT_LOCK:
        paths = [*node.files, str(feature.relative_to(ROOT))]
        for p in paths:
            subprocess.run(["git", "add", "--", p], cwd=ROOT, capture_output=True)
        # Oracle guardrail: a golden is committed only if it is explicitly in
        # files_touched. Otherwise we un-stage it (finding H3, scorecard anti-tamper).
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        for f in staged:
            if f.startswith("evals/golden/") and not any(
                paths_overlap(f, d) for d in node.files
            ):
                subprocess.run(
                    ["git", "reset", "-q", "HEAD", "--", f],
                    cwd=ROOT,
                    capture_output=True,
                )
                print(
                    f"⚠️  {node.id}: golden outside files_touched un-staged (oracle protected): {f}",
                    flush=True,
                )
        leftover = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
        ).stdout
        out_of_scope = [
            line
            for line in leftover.splitlines()
            if line and not line.startswith(("A ", "M ", "R ", "D "))
        ]
        if out_of_scope:
            print(
                f"⚠️  {node.id}: changes outside files_touched left uncommitted:",
                flush=True,
            )
            for line in out_of_scope[:10]:
                print(f"     {line}", flush=True)
        subprocess.run(["git", "commit", "-m", message], cwd=ROOT, capture_output=True)


def _build_base_prompt(node: Node, feature: Path) -> str:
    return (
        f"You act as the implementer agent (.claude/agents/implementer.md). "
        f"Read {feature}/spec.md then {feature}/design.md then {feature}/tasks.md. "
        f"Execute ONLY task {node.id} — {node.title}. "
        f"Respect its files_touched scope and its done_when. "
        f"If the spec is ambiguous or has gaps: do not invent, record the question (OQ-n format) in spec.md §8 "
        f"and end blocked. "
        f"You MUST end your reply with a single line: "
        f'"STATUS: done" or "STATUS: blocked — <reason, e.g. OQ-3>".\n{node.prompt}{node.rework}'
    )


def _run_verify(node: Node) -> tuple[bool, str, str]:
    """Run the task's `verify` (no shell). Returns (passed, agent_feedback, log_label)."""
    if not node.verify:
        return True, "", ""
    try:
        argv, venv = parse_verify(node.verify)
    except ValueError as e:
        # Should not happen (plan-lint already blocks), but defense in depth under
        # --force: we never launch a shell.
        return False, f"\n\n⛔ invalid verify (`{node.verify}`): {e}", "verify INVALID"
    v = subprocess.run(
        argv,
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, **venv} if venv else None,
    )
    if v.returncode != 0:
        return (
            False,
            f"\n\n⛔ verify failed (`{node.verify}`):\n{(v.stdout + v.stderr)[-2000:]}",
            "verify FAIL",
        )
    return True, "", ""


def _eval_gate(node: Node, real_ids: list[str]) -> tuple[bool, str]:
    """Run evals + anti-empty-gate (M6) + ID coverage (M7). Returns (ok, agent_feedback)."""
    ok, out = run_evals()
    # A task that touches source code MUST have evals even without a declared
    # implements (finding M6) — otherwise `just evals` green by absence (masked
    # exit-5) would let ungated code through.
    touches_source = any(
        f.endswith(".py") and not f.startswith(("tests/", "evals/")) for f in node.files
    ) or any(
        paths_overlap(f, p)
        for f in node.files
        for p in ("src", "app", "lib", "modules")
    )
    if ok and (real_ids or touches_source):
        collected = evals_collected()
        if "::" not in collected:
            reason = (
                f"implements {node.implements}"
                if real_ids
                else f"modifies source code {node.files}"
            )
            return False, (
                "Empty gate: `just evals` is green but NO eval is collected "
                f"while the task {reason}. Write the evals from spec.md §7 "
                "(pytest -m eval) — no eval, no done."
            )
        if real_ids:
            missing = [
                i
                for i in real_ids
                if i.startswith("EVAL-") and not eval_covers(i, collected)
            ]
            if missing:
                return False, (
                    f"Incomplete eval coverage: no collected test carries {missing}. "
                    f"Convention: node-id `test_{missing[0].lower().replace('-', '_')}_<case>` "
                    "(lowercased ID, dashes→underscores)."
                )
    return ok, out


def run_task(node: Node, feature: Path, dry: bool) -> str:
    """Returns done | failed | blocked. Per attempt: run the agent → parse the
    STATUS verdict → run verify → run the eval gate → scoped commit on green."""
    if dry:
        print(
            f"  [dry-run] {RUNNER.name} run: {node.id} "
            f"(acceptEdits, max_turns={MAX_TURNS}, {len(ALLOWED_TOOLS)} allowed tools)"
        )
        return "done"

    real_ids = list(
        dict.fromkeys(s for t in node.implements for s in SPEC_ID.findall(t))
    )
    trace = f"[{', '.join(real_ids)}]" if real_ids else "[auto]"
    mid = resolve_model("implementer", node.model, REGISTRY)
    base_prompt = _build_base_prompt(node, feature) + REGISTRY.profile_text(mid)
    session: str | None = None
    extra = ""
    for attempt in range(1, MAX_EVAL_RETRIES + 1):
        print(f"▶ {node.id} (attempt {attempt}/{MAX_EVAL_RETRIES})", flush=True)
        t0 = time.monotonic()
        if session:
            # Retry in the SAME session: the agent fixes its work instead of redoing it
            prompt = (
                f"Still on task {node.id} — {node.title}. Fix without rewriting everything:{extra}\n"
                f'End with "STATUS: done" or "STATUS: blocked — <reason>".'
            )
        else:
            prompt = base_prompt + extra
        r = run_claude(prompt, resume=session, model=mid)
        journal(
            feature,
            event="task_attempt",
            id=node.id,
            attempt=attempt,
            model=mid,
            duration_s=round(time.monotonic() - t0, 1),
            cost_usd=r["cost_usd"],
            session=r["session_id"],
            ok=r["ok"],
        )
        if not r["ok"]:
            print(r["error"], file=sys.stderr)
            run_log(feature, node, "implementer", f"claude error (t{attempt})")
            session = None  # unknown/lost session: start clean
            continue
        session = r["session_id"] or session

        sm = re.search(r"STATUS:\s*(done|blocked)([^\n]*)", r["text"], re.I)
        if sm and sm.group(1).lower() == "blocked":
            reason = sm.group(2).strip(" —-:") or "unspecified reason"
            run_log(feature, node, "implementer", f"BLOCKED — {reason}")
            journal(feature, event="task_blocked", id=node.id, reason=reason)
            notify(
                f"{node.id} blocked: {reason} — Owner response expected (spec.md §8)"
            )
            return "blocked"
        if not sm:
            print(
                f"⚠️  {node.id}: no STATUS line in the reply — falling back to the evals",
                flush=True,
            )

        passed, feedback, label = _run_verify(node)
        if not passed:
            extra = feedback
            run_log(feature, node, "implementer", f"{label} (t{attempt})")
            continue

        ok, out = _eval_gate(node, real_ids)
        if ok:
            run_log(feature, node, "implementer", f"done, evals green (t{attempt})")
            scoped_commit(
                node,
                feature,
                f"feat({feature.name}): {node.id} {node.title} {trace} [auto]",
            )
            journal(feature, event="task_done", id=node.id, attempts=attempt)
            return "done"
        extra = f"\n\n⛔ EVAL GATE RED on the previous attempt. Fix:\n{out}"
        run_log(feature, node, "eval-runner", f"FAIL (t{attempt})")
    notify(f"{node.id}: {MAX_EVAL_RETRIES} eval failures — Owner escalation")
    journal(feature, event="task_failed", id=node.id)
    return "failed"


REVIEW_LENSES = [
    "correctness: does the code do what the spec says (INV/BHV), values and bounds included",
    "spec/design conformance: traceability, scope, ADR compliance, no scope creep",
    "edge cases & robustness: extreme inputs, errors, does the deliverable actually run",
]


def pick_reviewer_models(cp: Node, n: int) -> list[str | None]:
    """n models for the panel. Separation of duties: we prefer a reviewer model
    DIFFERENT from the implementer (a model must not validate its own work alone)."""
    impl = resolve_model("implementer", "", REGISTRY)
    base = resolve_model("reviewer", cp.model, REGISTRY)
    pool = [m.id for m in REGISTRY.eligible("reviewer")] or ([base] if base else [None])
    # priority to models != implementer, then the rest
    ordered = [m for m in pool if m != impl] + [m for m in pool if m == impl]
    if base in ordered:  # keep the role default at the front if it is admissible
        ordered = [base] + [m for m in ordered if m != base]
    return [ordered[i % len(ordered)] for i in range(n)]


def _aggregate_verdict(verdicts: list[str]) -> str:
    if any(v == "BLOCK" for v in verdicts):
        return "BLOCK"
    if sum(v == "PASS" for v in verdicts) > len(verdicts) / 2:  # strict majority
        return "PASS"
    return "WARN"


def run_review(cp: Node, feature: Path, dry: bool) -> tuple[str, Path, bool]:
    """Reviewer panel. Returns (aggregated_verdict, report, self_review_only).
    self_review_only = True if all panelists run on the implementer's model
    (separation of duties impossible → self-validation will be refused)."""
    report = feature / ".runs" / f"{cp.id}-review.md"
    if dry:
        print(f"  [dry-run] reviewer×{cp.reviewers} → {report}")
        return "PASS", report, False

    n = cp.reviewers
    models = pick_reviewer_models(cp, n)
    impl = resolve_model("implementer", "", REGISTRY)
    verdicts: list[str] = []
    sections: list[str] = []
    for i, mid in enumerate(models):
        lens = REVIEW_LENSES[i % len(REVIEW_LENSES)] if n > 1 else "full review"
        prompt = (
            f"You act as the reviewer agent (.claude/agents/reviewer.md). Feature: {feature}. "
            f"Checkpoint {cp.id} — {cp.title}. Tasks covered: {', '.join(cp.depends_on) or 'all'}. "
            f"REVIEW LENS imposed: {lens}. "
            f"Produce the report (✅/⚠️/❌ with file:line) and you MUST end with a "
            f'single line: "VERDICT: PASS", "VERDICT: WARN" or "VERDICT: BLOCK".'
        ) + REGISTRY.profile_text(mid)
        r = run_claude(prompt, model=mid)
        vm = re.findall(r"VERDICT:\s*(PASS|WARN|BLOCK)", r["text"])
        v = vm[-1] if vm else "WARN"
        verdicts.append(v)
        sections.append(
            f"## Panelist {i + 1} — {mid or 'CLI default'} — lens: {lens}\nVERDICT: {v}\n\n{r['text'] or r['error']}"
        )
        journal(
            feature,
            event="review",
            id=cp.id,
            model=mid,
            lens=lens,
            verdict=v,
            cost_usd=r["cost_usd"],
            ok=r["ok"],
        )

    agg = _aggregate_verdict(verdicts)
    self_only = impl is not None and all(m == impl for m in models)
    report.parent.mkdir(exist_ok=True)
    header = f"# Review {cp.id} — panel of {n} — aggregated verdict: {agg} ({', '.join(verdicts)})\n\n"
    report.write_text(header + "\n\n---\n\n".join(sections), encoding="utf-8")
    return agg, report, self_only


def parse_rejection(path: Path) -> dict:
    info: dict = {"reason": "", "tasks": []}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("reason="):
            info["reason"] = line[len("reason=") :].strip()
        elif line.startswith("tasks="):
            info["tasks"] = line[len("tasks=") :].split()
    return info


def wait_checkpoint(
    node: Node, feature: Path, dry: bool, supervised: bool
) -> tuple[str, dict]:
    """Returns ("approved", {}) or ("rejected", {reason, tasks})."""
    approval = feature / ".approvals" / node.id
    rejection = feature / ".approvals" / f"{node.id}.rejected"
    if dry:
        print(
            f"  [dry-run] CHECKPOINT {node.id} (mode {node.mode}) — attend {approval}"
        )
        return "approved", {}

    verdict, report, self_only = run_review(node, feature, dry)
    evals_ok, _ = run_evals()

    if node.mode == "auto" and not supervised:
        if self_only:
            notify(
                f"{node.id} (auto): separation of duties impossible (reviewer = implementer's model) "
                "→ human validation required. Configure a distinct reviewer model in models/registry.toml."
            )
        elif verdict == "PASS" and evals_ok:
            approval.parent.mkdir(exist_ok=True)
            # Signed like a human approval (the orchestrator has the secret) to
            # stay verifiable if the token is re-read; "auto-approved" stays in
            # the author for traceability (finding H1, auto-path consistency).
            approval.write_text(
                approvals.sign(
                    feature,
                    node.id,
                    "auto-approved (evals green + reviewer panel PASS)",
                    datetime.now().isoformat(),
                )
            )
            run_log(
                feature,
                node,
                "reviewer",
                "checkpoint auto-validated (PASS, evals green)",
            )
            notify(f"{node.id} auto-validated — report: {report.relative_to(ROOT)}")
            return "approved", {}
        else:
            notify(
                f"{node.id} (auto): panel {verdict} / evals {'green' if evals_ok else 'RED'} → falling back to human validation"
            )

    notify(
        f"CHECKPOINT {node.id}: Owner decision → scripts/approve.sh {node.id} {feature.relative_to(ROOT)} "
        f'or scripts/reject.sh {node.id} {feature.relative_to(ROOT)} "reason" [Tn …] '
        f"(reviewer report: {report.relative_to(ROOT)}, verdict {verdict})"
    )
    print(f"⏸  {node.id} — waiting for {approval} (or .rejected)", flush=True)
    while True:
        if rejection.exists():
            info = parse_rejection(rejection)
            rejection.rename(
                rejection.parent
                / f"{node.id}.rejected.handled-{datetime.now():%Y%m%d%H%M%S}"
            )
            run_log(feature, node, "owner", f"checkpoint REJECTED — {info['reason']}")
            journal(feature, event="checkpoint_rejected", id=node.id, **info)
            notify(
                f"{node.id} rejected — reopening: {', '.join(info['tasks']) or 'all the checkpoint tasks'}"
            )
            return "rejected", info
        if approval.exists():
            ok, why = approvals.verify(
                feature, node.id, approval.read_text(encoding="utf-8")
            )
            if not ok:
                # Forged token / invalid signature: discard it and keep
                # waiting for a real human validation (finding H1).
                approval.rename(
                    approval.parent / f"{node.id}.invalid-{datetime.now():%Y%m%d%H%M%S}"
                )
                journal(
                    feature, event="checkpoint_forgery_rejected", id=node.id, why=why
                )
                notify(
                    f"⛔ {node.id}: approval REJECTED ({why}) — token discarded, "
                    "still waiting for a signed human validation."
                )
                continue
            if "unsigned" in why:
                notify(f"⚠️ {node.id}: approval accepted but {why}")
            # Consumed after honoring: a token does not replay (finding H4).
            approval.rename(
                approval.parent / f"{node.id}.handled-{datetime.now():%Y%m%d%H%M%S}"
            )
            run_log(feature, node, "owner", "checkpoint validated")
            notify(f"{node.id} validated — resuming execution")
            return "approved", {}
        time.sleep(20)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("feature", help="feature directory (contains tasks.md)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--validate", action="store_true", help="plan-lint: check tasks.md and exit"
    )
    ap.add_argument(
        "--supervised",
        action="store_true",
        help="force all checkpoints to blocking",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="ignore status approved + lint errors (not recommended)",
    )
    args = ap.parse_args()

    feature = (ROOT / args.feature).resolve()
    fm, nodes = parse_tasks_md(feature / "tasks.md")

    errors, warnings = validate(feature, fm, nodes, REGISTRY)
    if args.validate or errors or warnings:
        print(
            f"Plan-lint — {len(nodes)} nodes, frontmatter status: {fm.get('status', '∅')}"
        )
        for w in warnings:
            print(f"  ⚠️  {w}")
        for e in errors:
            print(f"  ❌ {e}")
        if not errors and not warnings:
            print("  ✅ no problem")
        if args.validate:
            # Surface every verify: the Owner signs these commands by approving the
            # plan (they will run on the host, without a shell — finding H2).
            verifs = [(n.id, n.verify) for n in nodes if n.verify]
            if verifs:
                print("\n  Verify commands (run without a shell, to validate):")
                for nid, vcmd in verifs:
                    print(f"    {nid}: {vcmd}")
    if args.validate:
        return 1 if errors else 0
    if errors and not args.force:
        print("⛔ Invalid plan — fix it (or --force, not recommended).")
        return 1

    if fm.get("status") != "approved" and not (args.dry_run or args.force):
        print(
            f"⛔ tasks.md has status '{fm.get('status')}' — a plan must be 'approved' by the Owner before execution."
        )
        return 1

    # Fail-closed (finding H1): a plan with checkpoints requires a signing
    # secret, otherwise any .approvals/<CP> file (which an agent can write via
    # Bash) would be honored. Without a secret we REFUSE to start, except with
    # explicit opt-in LAB_ALLOW_UNSIGNED_APPROVALS=1 (back-compat / legacy).
    has_checkpoint = any(n.is_checkpoint for n in nodes)
    # .strip(): an empty/blank secret counts as absent (consistent with approvals._secret).
    secret_set = bool((os.environ.get(approvals.ENV_SECRET) or "").strip())
    allow_unsigned = os.environ.get("LAB_ALLOW_UNSIGNED_APPROVALS") == "1"
    if has_checkpoint and not secret_set and not allow_unsigned and not args.dry_run:
        print(
            "⛔ Plan with a checkpoint but LAB_APPROVAL_SECRET not set: an "
            "unsigned approval would be forgeable by an agent (finding H1). "
            "Export LAB_APPROVAL_SECRET (recommended) or, knowingly, "
            "LAB_ALLOW_UNSIGNED_APPROVALS=1 to allow unsigned tokens."
        )
        return 1

    by_id = {n.id: n for n in nodes}
    print(f"Plan: {len(nodes)} nodes — " + ", ".join(n.id for n in nodes))
    if REGISTRY.models:
        roles_used = {
            "implementer": resolve_model("implementer", "", REGISTRY),
            "reviewer": resolve_model("reviewer", "", REGISTRY),
        }
        print(
            "Models (registry): "
            + ", ".join(f"{r}={m or 'CLI default'}" for r, m in roles_used.items())
        )

    rejections: dict[str, int] = {}
    state_f = feature / ".runs" / "state.json"
    state_f.parent.mkdir(exist_ok=True)
    if not args.dry_run:
        # Inter-process lock (finding H6): forbids two concurrent runs on the
        # same feature (race on state.json / git index / journal / budget).
        try:
            acquire_orchestrator_lock(feature)
        except OSError as e:
            print(f"⛔ {e}", file=sys.stderr)
            return 1
    if state_f.exists() and not args.dry_run:
        # Tolerant resume (finding L9): a truncated state.json (kill mid-write)
        # must not crash the resume — we start clean rather than crash.
        try:
            restored = json.loads(state_f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(
                f"⚠️  state.json unreadable ({e}) — fresh restart (all tasks pending).",
                file=sys.stderr,
            )
            restored = {}
        for nid, st in restored.items():
            if nid in by_id and st == "done":
                by_id[nid].status = "done"

    def save() -> None:
        if not args.dry_run:
            atomic_write_json(state_f, {n.id: n.status for n in nodes})

    while any(n.status == "pending" for n in nodes):
        if BUDGET_USD and COST_TOTAL["usd"] >= BUDGET_USD:
            notify(
                f"⛔ Budget reached: ${COST_TOTAL['usd']:.2f} ≥ ${BUDGET_USD:.2f} (LAB_BUDGET_USD) — "
                "stopping before the next wave. Restart after review (resume via .runs/state.json)."
            )
            journal(
                feature,
                event="budget_stop",
                spent_usd=round(COST_TOTAL["usd"], 4),
                cap_usd=BUDGET_USD,
            )
            return 1
        ready = [
            n
            for n in nodes
            if n.status == "pending"
            and all(by_id[d].status == "done" for d in n.depends_on if d in by_id)
        ]
        if not ready:
            print(
                "⛔ Deadlock: no ready task. Check the depends_on graph (--validate)."
            )
            return 1

        cps = [n for n in ready if n.is_checkpoint]
        tasks = [n for n in ready if not n.is_checkpoint]

        if tasks:
            wave = ", ".join(n.id for n in tasks)
            print(f"\n=== Parallel wave: {wave} ===")
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as ex:
                futs = {ex.submit(run_task, n, feature, args.dry_run): n for n in tasks}
                for fut in as_completed(futs):
                    n = futs[fut]
                    n.status = fut.result()
                    if n.status in ("failed", "blocked"):
                        skip_dependents(n, nodes)
                    save()
        for cp in cps:
            outcome, info = wait_checkpoint(cp, feature, args.dry_run, args.supervised)
            if outcome == "approved":
                cp.status = "done"
            else:  # rejected — on_reject: back to the targeted tasks with a comment
                rejections[cp.id] = rejections.get(cp.id, 0) + 1
                if rejections[cp.id] > MAX_CP_REJECTS:
                    cp.status = "failed"
                    notify(
                        f"{cp.id}: rejected {rejections[cp.id]} times — stopping, manual resume required"
                    )
                    skip_dependents(cp, nodes)
                else:
                    targets = info["tasks"] or list(cp.depends_on)
                    for tid in targets:
                        t = by_id.get(tid)
                        if t and not t.is_checkpoint:
                            t.status = "pending"
                            t.rework = (
                                f"\n\n⚠️ OWNER REVIEW FEEDBACK (rejection {cp.id}): {info['reason']}\n"
                                f"Fix accordingly before re-delivering."
                            )
                    cp.status = "pending"  # re-triggered when the tasks come back done
            save()

    bad = [n for n in nodes if n.status in ("failed", "blocked", "skipped")]
    print("\n=== Summary ===")
    for n in nodes:
        mark = {"done": "✅", "failed": "❌", "blocked": "🛑", "skipped": "⏭"}.get(
            n.status, "·"
        )
        print(f"  {mark} {n.id} — {n.status}")
    print(f"  Σ agent cost: ${COST_TOTAL['usd']:.2f} (detail: .runs/journal.jsonl)")
    journal(
        feature,
        event="run_end",
        cost_usd_total=round(COST_TOTAL["usd"], 4),
        statuses={n.id: n.status for n in nodes},
    )
    if bad:
        notify(
            f"{feature.name}: run finished with {len(bad)} node(s) not done — "
            "answer the blocks then restart (resume via .runs/state.json)."
        )
        return 1
    notify(f"🎉 {feature.name}: all tasks are done. Merge = human decision (final CP).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
