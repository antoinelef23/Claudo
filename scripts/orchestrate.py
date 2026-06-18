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
    collected (no eval written = no done, even if `make evals` exits 0)
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
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import approvals
from registry import load_registry, resolve_model

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
CLAUDE_ARGS = [
    "--permission-mode",
    "acceptEdits",
    "--max-turns",
    "100",
    # headless: acceptEdits covers edits, not Bash — minimal whitelist so the
    # implementer can run its tests (otherwise it codes blind)
    "--allowedTools",
    "Bash(uv:*),Bash(make:*),Bash(python3:*),Bash(mkdir:*),Bash(ls:*),Bash(git diff:*),Bash(git log:*)",
    # structured output: result + session_id (retry resume) + total_cost_usd (journal)
    "--output-format",
    "json",
]
SPEC_ID = re.compile(r"\b(?:INV|BHV|EX|EVAL|NG)-[A-Za-z0-9]+\b")

# Commands allowed as a task's `verify` (finding H2). A verify is a test/build
# command, never a shell: we run it WITHOUT a shell (argv), and plan-lint rejects
# any command outside this list or containing shell metacharacters. Prevents an
# agent-generated `verify` of the form `pytest; curl|sh`.
VERIFY_ALLOWED = {
    "true",
    "false",
    "test",
    "[",
    "ls",
    "cat",
    "grep",
    "head",
    "tail",
    "make",
    "uv",
    "python",
    "python3",
    "pytest",
    "ruff",
}
# Metacharacters that would only make sense via a shell — forbidden in a verify.
_SHELL_META = re.compile(r"[;&|`$><\n]")
# Env prefixes `VAR=val` allowed before a verify (finding H2, env smuggling).
# Allowlist: keys that add NO privilege beyond what the verify already does
# (it runs in-repo agent code: conftest.py, test modules). PYTHONPATH is one of
# them — `PYTHONPATH=src uv run …` is standard usage and grants no more than the
# `Bash(uv:*)/Bash(python3:*)` the agent already has.
# Refused (blocked): keys that hijack OTHER processes/shells/binaries —
# LD_PRELOAD, LD_LIBRARY_PATH, DYLD_*, BASH_ENV, ENV, PYTHONSTARTUP, PYTHONHOME, PATH —
# which would be a real escalation (RCE without a shell, outside the test scope).
VERIFY_ENV_ALLOWED = {
    "CI",
    "TZ",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "NO_COLOR",
    "PYTHONPATH",
    "PYTHONDONTWRITEBYTECODE",
    "PYTEST_ADDOPTS",
}

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


@dataclass
class Node:
    id: str
    title: str
    is_checkpoint: bool
    depends_on: list[str] = field(default_factory=list)
    prompt: str = ""
    implements: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    verify: str = ""
    done_when: str = ""
    mode: str = "blocking"  # checkpoints: blocking | auto
    status: str = "pending"  # pending | running | done | failed | blocked | skipped
    rework: str = ""  # Owner comment after a checkpoint rejection (passed to the agent)
    model: str = ""  # task model override (otherwise: registry role default)
    reviewers: int = 1  # size of the reviewer panel (checkpoint) — >=2 = majority vote


def parse_tasks_md(path: Path) -> tuple[dict, list[Node]]:
    text = path.read_text(encoding="utf-8")

    fm = {}
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                fm[k.strip()] = v.split("#")[0].strip()

    nodes: list[Node] = []
    sections = re.split(r"\n### ", text)
    for sec in sections[1:]:
        header, _, body = sec.partition("\n")
        hm = re.match(r"(T\d+|CP-\d+)\s*—\s*(.*)", header.strip())
        if not hm:
            continue
        nid, title = hm.group(1), hm.group(2).strip()
        is_cp = nid.startswith("CP")

        deps: list[str] = []
        dm = re.search(r"\*\*depends_on\s*:?\*\*\s*\[([^\]]*)\]", body)
        if dm:
            deps = [d.strip() for d in dm.group(1).split(",") if d.strip()]
        if is_cp:
            tm = re.search(
                r"\*\*trigger\s*:?\*\*[^\n]*?(?:quand|when)\s+\[?([T\d\s,]+?)\]?\s+(?:(?:sont|are)\s+)?done",
                body,
            )
            if tm:
                deps = [d.strip() for d in tm.group(1).split(",") if d.strip()]

        pm = re.search(r"\*\*prompt\s*:?\*\*\s*\n?((?:\s*>.*\n?)+)", body)
        prompt = ""
        if pm:
            prompt = "\n".join(
                line.strip().lstrip("> ") for line in pm.group(1).splitlines()
            ).strip()
        if not prompt:
            pm = re.search(r"\*\*prompt\s*:?\*\*\s*([^\n]+)", body)
            if pm:
                prompt = pm.group(1).strip()

        node = Node(nid, title, is_cp, deps, prompt)

        im = re.search(r"\*\*implements\s*:?\*\*\s*\[([^\]]*)\]", body)
        if im:
            node.implements = [t.strip() for t in im.group(1).split(",") if t.strip()]
        fmm = re.search(r"\*\*files_touched\s*:?\*\*\s*([^\n]+)", body)
        if fmm:
            node.files = re.findall(r"`([^`]+)`", fmm.group(1))
        vm = re.search(r"\*\*verify\s*:?\*\*\s*`([^`]+)`", body)
        if vm:
            node.verify = vm.group(1).strip()
        dw = re.search(r"\*\*done_when\s*:?\*\*\s*([^\n]+)", body)
        if dw:
            node.done_when = dw.group(1).strip()
        mm = re.search(r"\*\*mode\s*:?\*\*\s*(auto|blocking)", body)
        if mm:
            node.mode = mm.group(1)
        mom = re.search(r"\*\*model\s*:?\*\*\s*`?([\w.\-]+)`?", body)
        if mom:
            node.model = mom.group(1)
        rm = re.search(r"\*\*reviewers\s*:?\*\*\s*(\d+)", body)
        if rm:
            node.reviewers = max(1, int(rm.group(1)))

        nodes.append(node)

    # Each task implicitly depends on every checkpoint defined before it
    last_cp: str | None = None
    for n in nodes:
        if n.is_checkpoint:
            last_cp = n.id
        elif last_cp and last_cp not in n.depends_on and not n.depends_on:
            n.depends_on.append(last_cp)
    return fm, nodes


# ---------------------------------------------------------------- plan-lint


def _ancestors(nodes: list[Node]) -> dict[str, set[str]]:
    by_id = {n.id: n for n in nodes}
    memo: dict[str, set[str]] = {}

    def walk(nid: str, stack: tuple[str, ...] = ()) -> set[str]:
        if nid in memo:
            return memo[nid]
        if nid in stack:  # cycle — flagged by validate(), we cut here
            return set()
        acc: set[str] = set()
        for d in by_id.get(nid, Node(nid, "", False)).depends_on:
            acc.add(d)
            acc |= walk(d, (*stack, nid))
        memo[nid] = acc
        return acc

    return {n.id: walk(n.id) for n in nodes}


def _paths_overlap(a: str, b: str) -> bool:
    a, b = a.strip().rstrip("/"), b.strip().rstrip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def parse_verify(cmd: str) -> tuple[list[str], dict[str, str]]:
    """Split a `verify` command into (argv, env_overrides) — WITHOUT a shell (finding H2).

    Handles environment prefixes `VAR=val` restricted to VERIFY_ENV_ALLOWED
    (e.g. `CI=1 …`, `PYTHONPATH=src uv run …`). Keys that hijack other
    processes/shells/binaries (LD_PRELOAD, DYLD_*, BASH_ENV, PYTHONSTARTUP, PATH…)
    are refused: that would be an RCE escalation outside the test scope.
    Raises ValueError if: shell metacharacters, unparsable (unclosed quotes),
    empty, or command outside VERIFY_ALLOWED. The caller then runs the argv
    as-is (`shell=False`), which neutralizes any chaining/injection even if this
    validation were bypassed.
    """
    if _SHELL_META.search(cmd):
        raise ValueError(
            "shell metacharacters forbidden in verify (; & | $ ` > < newline) — "
            "a verify is a single command, not a shell script"
        )
    tokens = shlex.split(cmd)  # may raise ValueError (unclosed quotes)
    env: dict[str, str] = {}
    while tokens and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0]):
        k, _, v = tokens[0].partition("=")
        if k not in VERIFY_ENV_ALLOWED:
            raise ValueError(
                f'environment prefix "{k}=" forbidden in verify — '
                f"allowed keys: {', '.join(sorted(VERIFY_ENV_ALLOWED))}. "
                "PYTHONPATH/PYTHONSTARTUP/LD_PRELOAD/BASH_ENV… let you inject "
                "code loaded by the command (RCE without a shell)."
            )
        env[k] = v
        tokens = tokens[1:]
    if not tokens:
        raise ValueError("empty verify (after any environment prefixes)")
    prog = Path(tokens[0]).name
    if prog not in VERIFY_ALLOWED:
        raise ValueError(
            f'verify command "{tokens[0]}" outside allowlist — '
            f"allowed: {', '.join(sorted(VERIFY_ALLOWED))}"
        )
    return tokens, env


def validate(feature: Path, fm: dict, nodes: list[Node]) -> tuple[list[str], list[str]]:
    """Plan-lint. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    by_id = {n.id: n for n in nodes}

    if not nodes:
        return (["no task recognized — check the format `### T1 — title`"], [])
    seen: set[str] = set()
    for n in nodes:
        if n.id in seen:
            errors.append(f"{n.id}: duplicate ID")
        seen.add(n.id)

    # Graph
    for n in nodes:
        for d in n.depends_on:
            if d not in by_id:
                errors.append(f"{n.id}: depends_on [{d}] does not exist")
    # Cycles (DFS coloring)
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n.id: WHITE for n in nodes}

    def dfs(nid: str) -> bool:
        color[nid] = GREY
        for d in by_id[nid].depends_on:
            if d not in by_id:
                continue
            if color[d] == GREY:
                errors.append(f"dependency cycle via {nid} → {d}")
                return True
            if color[d] == WHITE and dfs(d):
                return True
        color[nid] = BLACK
        return False

    for n in nodes:
        if color[n.id] == WHITE and dfs(n.id):
            break

    # Mandatory task fields
    for n in nodes:
        if n.is_checkpoint:
            continue
        if not n.done_when:
            errors.append(
                f'{n.id}: done_when missing (nothing executable defines "done")'
            )
        if not n.files:
            errors.append(
                f"{n.id}: files_touched missing or without backticks (parallelism unverifiable)"
            )
        if not n.prompt:
            warnings.append(
                f"{n.id}: empty prompt — the implementer will only have the title"
            )
        if not n.verify:
            warnings.append(
                f"{n.id}: no executable verify — done_when will not be checked mechanically"
            )
        else:
            try:
                parse_verify(n.verify)
            except ValueError as e:
                errors.append(f"{n.id}: invalid verify (`{n.verify}`) — {e}")

    # Spec IDs
    spec_path = feature / "spec.md"
    if spec_path.exists():
        spec_text = spec_path.read_text(encoding="utf-8")
        for n in nodes:
            for tok in n.implements:
                for sid in SPEC_ID.findall(tok):
                    if sid not in spec_text:
                        errors.append(
                            f"{n.id}: implements [{sid}] not found in spec.md"
                        )
        # Each EVAL-n declared in the spec must be carried by a task
        claimed = {s for n in nodes for t in n.implements for s in SPEC_ID.findall(t)}
        for ev in sorted(set(re.findall(r"\bEVAL-\w+\b", spec_text))):
            if ev not in claimed:
                warnings.append(
                    f"{ev} declared in spec.md §7 but carried by no task (implements)"
                )
        # finding L4: ID coverage only validates EVAL-*. A plan that implements
        # behaviors/invariants WITHOUT any EVAL-* relies on off-plan tests — we
        # flag it (the hard gate stays on EVAL-*).
        impl_behaviors = {
            s
            for n in nodes
            for t in n.implements
            for s in SPEC_ID.findall(t)
            if s.startswith(("BHV-", "INV-"))
        }
        if impl_behaviors and not any(s.startswith("EVAL-") for s in claimed):
            warnings.append(
                f"behaviors/invariants are implemented ({sorted(impl_behaviors)[:3]}…) "
                "but no task carries an EVAL-*: eval coverage relies on off-plan tests"
            )
        # Documentation drift: the "# version : x.y.z" pointers must track the spec
        sv = re.search(r"^version:\s*([\d.]+)", spec_text, re.M)
        if sv:
            for art in ("tasks.md", "design.md"):
                p = feature / art
                if not p.exists():
                    continue
                m = re.search(
                    r"^spec:.*?version\s*:?\s*([\d.]+)",
                    p.read_text(encoding="utf-8"),
                    re.M,
                )
                if m and m.group(1) != sv.group(1):
                    warnings.append(
                        f"{art} references spec v{m.group(1)} but spec.md is at v{sv.group(1)} — "
                        f"documentation drift, update the pointer after the amendment"
                    )
    else:
        errors.append("spec.md not found next to tasks.md")

    # Parallelism safety: two unordered tasks must not share any path
    anc = _ancestors(nodes)
    tasks = [n for n in nodes if not n.is_checkpoint]
    for i, a in enumerate(tasks):
        for b in tasks[i + 1 :]:
            if a.id in anc[b.id] or b.id in anc[a.id]:
                continue  # ordered by the DAG
            clash = [
                (fa, fb) for fa in a.files for fb in b.files if _paths_overlap(fa, fb)
            ]
            if clash:
                errors.append(
                    f"{a.id} ∥ {b.id}: runnable in parallel but files_touched overlap "
                    f"({clash[0][0]} ↔ {clash[0][1]}) — add a depends_on or separate the paths"
                )

    # Checkpoints
    cps = [n for n in nodes if n.is_checkpoint]
    if not cps:
        warnings.append(
            "no checkpoint — a plan without a human pause violates CLAUDE.md (hard rules)"
        )
    dependents = {n.id: [m.id for m in nodes if n.id in m.depends_on] for n in nodes}
    for cp in cps:
        if not cp.depends_on:
            warnings.append(
                f'{cp.id}: trigger not parsed — add "trigger : auto when [Tn, Tm] done"'
            )
        is_sink = not dependents[cp.id]
        mentions_merge = "merge" in (cp.title + " ").lower()
        if cp.mode == "auto" and (is_sink or mentions_merge):
            errors.append(
                f"{cp.id}: a final/merge checkpoint cannot be mode auto — the merge is human, always"
            )

    # Separation of duties: one model should not both implement AND arbitrate alone
    if REGISTRY.models:
        impl = REGISTRY.role_default("implementer")
        rev = REGISTRY.role_default("reviewer")
        if impl and impl == rev:
            warnings.append(
                f"separation of duties: reviewer and implementer point to the same model ({impl}) — "
                "an auto checkpoint will not be able to self-validate (will fall back to human). "
                "Assign a distinct reviewer model in models/registry.toml."
            )

    # Models: a task override must name a model eligible for its role
    if REGISTRY.models:
        for n in nodes:
            if not n.model:
                continue
            role = "reviewer" if n.is_checkpoint else "implementer"
            m = REGISTRY.by_id(n.model)
            if m is None:
                warnings.append(
                    f'{n.id}: model "{n.model}" absent from the registry (models/registry.toml)'
                )
            elif role not in m.roles:
                warnings.append(
                    f'{n.id}: model "{n.model}" not eligible for role {role} (registry: {m.roles})'
                )

    return errors, warnings


# ---------------------------------------------------------------- execution


def _gchat(msg: str) -> None:
    """Google Chat notification (opt-in). No-op if LAB_GCHAT_WEBHOOK absent; never crashes.
    Lets a squad (not just the Owner at their Mac) see checkpoints/blocks."""
    url = os.environ.get("LAB_GCHAT_WEBHOOK")
    if not url:
        return
    try:
        import json as _json
        import urllib.request

        req = urllib.request.Request(
            url,
            data=_json.dumps({"text": f"[Lab IA-natif] {msg}"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def notify(msg: str) -> None:
    print(f"🔔 {msg}", flush=True)
    if os.environ.get(
        "LAB_NO_NOTIFY"
    ):  # tests / CI: no external notification (incl. _gchat)
        return
    _gchat(msg)
    try:
        # msg passed as argv (item 1 of argv), NEVER interpolated into the
        # AppleScript source: an agent-generated `reason` can no longer inject a
        # `do shell script` via osascript (finding M2).
        subprocess.run(
            [
                "osascript",
                "-e",
                "on run argv",
                "-e",
                'display notification (item 1 of argv) with title (item 2 of argv) sound name "Glass"',
                "-e",
                "end run",
                msg,
                "Lab IA-natif",
            ],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass


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
    cmd = ["claude", "-p", prompt, *CLAUDE_ARGS]
    if model:
        cmd += ["--model", model]
    if resume:
        cmd += ["--resume", resume]
    # The approval secret must NEVER be visible to a sub-agent: otherwise
    # it could sign its own checkpoint validation (finding H1).
    child_env = {k: v for k, v in os.environ.items() if k != approvals.ENV_SECRET}
    try:
        p = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=TASK_TIMEOUT_S,
            env=child_env,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "text": "",
            "session_id": None,
            "cost_usd": 0.0,
            "error": f"timeout: agent killed after {TASK_TIMEOUT_S}s (LAB_TASK_TIMEOUT)",
        }
    if p.returncode != 0:
        return {
            "ok": False,
            "text": p.stdout,
            "session_id": None,
            "cost_usd": 0.0,
            "error": p.stderr[-2000:] or p.stdout[-2000:],
        }
    text, session_id, cost = p.stdout, None, 0.0
    try:
        data = json.loads(p.stdout)
        text = data.get("result") or ""
        session_id = data.get("session_id")
        cost = float(data.get("total_cost_usd") or 0.0)
    except (json.JSONDecodeError, TypeError):
        pass  # non-JSON output: keep the raw text
    with COST_LOCK:
        COST_TOTAL["usd"] += cost
    return {
        "ok": True,
        "text": text,
        "session_id": session_id,
        "cost_usd": cost,
        "error": "",
    }


def run_evals() -> tuple[bool, str]:
    p = subprocess.run(
        ["make", "-s", "evals"], cwd=ROOT, capture_output=True, text=True
    )
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
                _paths_overlap(f, d) for d in node.files
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


def run_task(node: Node, feature: Path, dry: bool) -> str:
    """Returns done | failed | blocked."""
    base_prompt = (
        f"You act as the implementer agent (.claude/agents/implementer.md). "
        f"Read {feature}/spec.md then {feature}/design.md then {feature}/tasks.md. "
        f"Execute ONLY task {node.id} — {node.title}. "
        f"Respect its files_touched scope and its done_when. "
        f"If the spec is ambiguous or has gaps: do not invent, record the question (OQ-n format) in spec.md §8 "
        f"and end blocked. "
        f"You MUST end your reply with a single line: "
        f'"STATUS: done" or "STATUS: blocked — <reason, e.g. OQ-3>".\n{node.prompt}{node.rework}'
    )
    if dry:
        print(f"  [dry-run] claude -p '<prompt {node.id}>' {' '.join(CLAUDE_ARGS)}")
        return "done"

    real_ids = list(
        dict.fromkeys(s for t in node.implements for s in SPEC_ID.findall(t))
    )
    trace = f"[{', '.join(real_ids)}]" if real_ids else "[auto]"

    mid = resolve_model("implementer", node.model, REGISTRY)
    base_prompt += REGISTRY.profile_text(mid)
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

        if node.verify:
            try:
                argv, venv = parse_verify(node.verify)
            except ValueError as e:
                # Should not happen (plan-lint already blocks), but defense in
                # depth if run under --force: we never launch a shell.
                extra = f"\n\n⛔ invalid verify (`{node.verify}`): {e}"
                run_log(feature, node, "implementer", f"verify INVALID (t{attempt})")
                continue
            v = subprocess.run(
                argv,
                cwd=ROOT,
                capture_output=True,
                text=True,
                env={**os.environ, **venv} if venv else None,
            )
            if v.returncode != 0:
                extra = f"\n\n⛔ verify failed (`{node.verify}`):\n{(v.stdout + v.stderr)[-2000:]}"
                run_log(feature, node, "implementer", f"verify FAIL (t{attempt})")
                continue

        ok, out = run_evals()
        # Anti-empty-gate: a task that touches source code MUST have evals,
        # even without a declared implements (finding M6) — otherwise `make evals`
        # green by absence (masked exit-5) would let ungated code through.
        touches_source = any(
            f.endswith(".py") and not f.startswith(("tests/", "evals/"))
            for f in node.files
        ) or any(
            _paths_overlap(f, p)
            for f in node.files
            for p in ("src", "app", "lib", "modules")
        )
        if ok and (real_ids or touches_source):
            collected = evals_collected()
            if "::" not in collected:
                ok = False
                reason = (
                    f"implements {node.implements}"
                    if real_ids
                    else f"modifies source code {node.files}"
                )
                out = (
                    "Empty gate: `make evals` is green but NO eval is collected "
                    f"while the task {reason}. Write the evals from spec.md §7 "
                    "(pytest -m eval) — no eval, no done."
                )
            elif real_ids:
                # ID coverage: pytest node-id matching (finding M7).
                missing = [
                    i
                    for i in real_ids
                    if i.startswith("EVAL-") and not eval_covers(i, collected)
                ]
                if missing:
                    ok = False
                    out = (
                        f"Incomplete eval coverage: no collected test carries {missing}. "
                        f"Convention: node-id `test_{missing[0].lower().replace('-', '_')}_<case>` "
                        "(lowercased ID, dashes→underscores)."
                    )
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


def skip_dependents(failed: Node, nodes: list[Node]) -> None:
    """Containment: only the (transitive) dependents of a failure are neutralized."""
    by_id = {n.id: n for n in nodes}
    queue = [failed.id]
    while queue:
        cur = queue.pop()
        for n in nodes:
            if n.status == "pending" and cur in n.depends_on:
                n.status = "skipped"
                print(f"⏭  {n.id} skipped (depends on {cur})", flush=True)
                queue.append(n.id)
    _ = by_id  # readability


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

    errors, warnings = validate(feature, fm, nodes)
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
