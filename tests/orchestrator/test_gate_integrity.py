"""P0 gate-integrity suite — the "green must mean green" invariants.

Covers the three fixes that close the working-tree≠HEAD divergence class:
  Fix 1  — scoped_commit fails CLOSED on out-of-scope changes (no silent drop), with
           whole-plan scope and a baseline for pre-existing dirt.
  Fix 2a — a checkpoint runs the FULL gate (via `just gate-ci`), not evals alone, and a
           dependency-manifest commit re-runs it immediately.
  Fix 2b — the merge checkpoint gates a CLEAN checkout of HEAD (throwaway worktree).
"""

from __future__ import annotations

import json
from pathlib import Path

from .conftest import approve, run_orch

FM = "---\ntype: tasks\nfeature: feat\nstatus: approved\n---\n\n# Tasks — feat\n"


def write_tasks(sandbox: Path, body: str) -> None:
    (sandbox / "work" / "feat" / "tasks.md").write_text(FM + body)


def state(sandbox: Path) -> dict:
    return json.loads((sandbox / "work" / "feat" / ".runs" / "state.json").read_text())


def events(sandbox: Path) -> list[dict]:
    p = sandbox / "work" / "feat" / ".runs" / "journal.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def handled_token(sandbox: Path, cp: str) -> str:
    # Auto-approval leaves the signed token at .approvals/<cp> (returns directly); the
    # human waiting-loop consumes it and renames to .handled-*. Check both.
    d = sandbox / "work" / "feat" / ".approvals"
    live = d / cp
    if live.exists():
        return live.read_text()
    hits = sorted(d.glob(f"{cp}.handled-*"))
    return hits[-1].read_text() if hits else ""


# --------------------------------------------------------- Fix 1: fail-closed scope


def test_out_of_scope_source_file_blocks(sandbox: Path) -> None:
    # A task that creates a SOURCE file no node declares is the L-1 footgun: committing
    # its own scope alone would drop this file, so the working tree looks green while
    # HEAD is broken. It must fail-closed, not silently succeed.
    (sandbox / ".shim" / "T1.sh").write_text(
        'echo data > t1.txt\nmkdir -p src && echo "x = 1" > src/foreign.py\n'
        'echo "STATUS: done"\n'
    )
    write_tasks(
        sandbox,
        """
### T1 — Declares t1.txt but also writes an undeclared source module
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`
""",
    )
    r = run_orch(sandbox)
    assert r.returncode == 1
    assert state(sandbox)["T1"] == "failed"
    assert any(e["event"] == "task_scope_violation" for e in events(sandbox))
    # The dropped file never reached HEAD.
    import subprocess

    hist = subprocess.run(
        ["git", "log", "-p", "--", "src/foreign.py"],
        cwd=sandbox,
        capture_output=True,
        text=True,
    ).stdout
    assert "x = 1" not in hist


def test_untracked_non_source_noise_is_not_a_violation(sandbox: Path) -> None:
    # Scratch/log noise out of scope must NOT block — only source/tracked drops matter,
    # else the real signal drowns.
    (sandbox / ".shim" / "T1.sh").write_text(
        'echo data > t1.txt\necho scratch > notes.log\necho "STATUS: done"\n'
    )
    write_tasks(
        sandbox,
        """
### T1 — Writes its file plus a scratch log
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`
""",
    )
    r = run_orch(sandbox)
    assert r.returncode == 0, r.stdout + r.stderr
    assert state(sandbox)["T1"] == "done"


def test_sibling_declared_file_is_in_plan_scope(sandbox: Path) -> None:
    # A file DECLARED by another node is part of the plan scope: a task producing it
    # (parallel wave timing) is not falsely blamed — that node will commit it.
    # evals-collect stub satisfies the M6 anti-empty-gate for the source files.
    (sandbox / "justfile").write_text(
        "evals:\n    #!/usr/bin/env bash\n    echo ok\n"
        "\nevals-collect:\n    @echo 'tests/x.py::test_eval_1_nominal'\n"
    )
    (sandbox / ".shim" / "T1.sh").write_text(
        'mkdir -p src\necho "a=1" > src/a.py\necho "b=1" > src/b.py\n'
        'echo "STATUS: done"\n'
    )
    write_tasks(
        sandbox,
        """
### T1 — Owns src/a.py, also lands src/b.py which T2 declares
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `src/a.py`
- **done_when :** ok
- **verify :** `true`

### T2 — Owns src/b.py
- **depends_on :** [T1]
- **implements :** [doc]
- **files_touched :** `src/b.py`
- **done_when :** ok
- **verify :** `true`
""",
    )
    r = run_orch(sandbox)
    # src/b.py is in the declared plan scope (T2 owns it) → no violation for T1.
    assert r.returncode == 0, r.stdout + r.stderr
    assert state(sandbox)["T1"] == "done"


def test_baseline_dirt_not_attributed_to_task(sandbox: Path) -> None:
    # A source file already dirty BEFORE the run (the Owner's own work) must not be
    # blamed on the first task. The clean-HEAD merge gate is the backstop.
    (sandbox / "preexisting.py").write_text("owner = 'wip'\n")  # untracked at start
    (sandbox / ".shim" / "T1.sh").write_text(
        'echo data > t1.txt\necho "STATUS: done"\n'
    )
    write_tasks(
        sandbox,
        """
### T1 — Clean task, unrelated to the pre-existing dirt
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`
""",
    )
    r = run_orch(sandbox)
    assert r.returncode == 0, r.stdout + r.stderr
    assert state(sandbox)["T1"] == "done"


# --------------------------------------------------- Fix 2a: full gate at checkpoint


def _justfile(evals_ok: bool = True, gate_ci: str | None = None) -> str:
    ev = '    echo "[stub] evals ok"\n' if evals_ok else "    exit 1\n"
    jf = "evals:\n    #!/usr/bin/env bash\n" + ev
    if gate_ci is not None:
        jf += "\ngate-ci:\n    #!/usr/bin/env bash\n" + gate_ci
    return jf


def _gate_at(sandbox: Path, cp: str) -> dict:
    hits = [
        e for e in events(sandbox) if e["event"] == "checkpoint_gate" and e["id"] == cp
    ]
    return hits[-1] if hits else {}


def test_full_gate_red_blocks_auto_approve(sandbox: Path) -> None:
    # A RED full gate (lint/config/brand drift `just evals` would miss) must block the
    # AUTO (mid) checkpoint and fall back to human validation — it must not auto-approve.
    # CP-1 is a mid checkpoint (auto); CP-2 is the always-human merge.
    (sandbox / "justfile").write_text(_justfile(gate_ci="    exit 1\n"))
    write_tasks(
        sandbox,
        """
### T1 — A
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`

### CP-1 — CHECKPOINT : mid gate
- **trigger :** auto quand [T1] done
- **validator :** Owner
- **mode :** auto

### T2 — B
- **depends_on :** [CP-1]
- **implements :** [doc]
- **files_touched :** `t2.txt`
- **done_when :** ok
- **verify :** `true`

### CP-2 — CHECKPOINT : merge
- **trigger :** auto quand [T2] done
- **validator :** Owner
- **mode :** blocking
""",
    )
    approve(
        sandbox, "CP-1"
    )  # auto must fall back to this human token, not self-approve
    approve(sandbox, "CP-2")
    r = run_orch(sandbox)
    assert r.returncode == 0, r.stdout + r.stderr
    # The auto checkpoint saw the full gate RED...
    assert _gate_at(sandbox, "CP-1").get("full_gate") == "RED"
    # ...and was NOT auto-approved (it used the human token).
    assert "auto-approved" not in handled_token(sandbox, "CP-1")


def test_full_gate_green_auto_approves(sandbox: Path) -> None:
    # Control: a GREEN full gate + reviewer PASS auto-approves the mid checkpoint, and
    # the (human) merge checkpoint records the clean-HEAD gate too (Fix 2b wired).
    (sandbox / "justfile").write_text(_justfile(gate_ci='    echo "gate ok"\n'))
    import subprocess

    subprocess.run(["git", "add", "justfile"], cwd=sandbox, capture_output=True)
    subprocess.run(
        ["git", "commit", "-qm", "add gate-ci"], cwd=sandbox, capture_output=True
    )
    write_tasks(
        sandbox,
        """
### T1 — A
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`

### CP-1 — CHECKPOINT : mid gate
- **trigger :** auto quand [T1] done
- **validator :** Owner
- **mode :** auto

### T2 — B
- **depends_on :** [CP-1]
- **implements :** [doc]
- **files_touched :** `t2.txt`
- **done_when :** ok
- **verify :** `true`

### CP-2 — CHECKPOINT : merge
- **trigger :** auto quand [T2] done
- **validator :** Owner
- **mode :** blocking
""",
    )
    approve(sandbox, "CP-2")  # merge is always human
    r = run_orch(sandbox)
    assert r.returncode == 0, r.stdout + r.stderr
    # Mid CP auto-approved on a green full gate; it is not the merge so no clean-HEAD gate.
    assert "auto-approved" in handled_token(sandbox, "CP-1")
    assert _gate_at(sandbox, "CP-1").get("full_gate") == "green"
    assert _gate_at(sandbox, "CP-1").get("head_gate") == "n/a"
    # Merge CP ⇒ clean-HEAD gate actually ran (throwaway worktree) and passed.
    assert _gate_at(sandbox, "CP-2").get("head_gate") == "green"


def test_dep_manifest_commit_triggers_full_gate(sandbox: Path) -> None:
    # Committing a dependency manifest re-runs the full gate immediately (a dep install
    # can silently turn committed evals red) — a `dep_gate` event proves it fired.
    (sandbox / ".shim" / "T1.sh").write_text(
        'printf "[project]\\nname=\'x\'\\n" > pyproject.toml\necho "STATUS: done"\n'
    )
    write_tasks(
        sandbox,
        """
### T1 — Adds a dependency manifest
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `pyproject.toml`
- **done_when :** ok
- **verify :** `true`
""",
    )
    r = run_orch(sandbox)
    assert r.returncode == 0, r.stdout + r.stderr
    assert any(e["event"] == "dep_gate" for e in events(sandbox))


# ------------------------------------------- Fix 2b: clean-HEAD catches divergence


def test_clean_head_gate_catches_working_tree_only_green(sandbox: Path) -> None:
    # The core of Fix 2b: gate-ci passes only if marker.txt exists. The marker is present
    # in the working tree (untracked baseline) but NEVER committed → the working-tree gate
    # is GREEN while a clean checkout of HEAD is RED. Only the clean-HEAD merge gate can
    # see this working-tree≠HEAD divergence — exactly the class the per-task gate is blind
    # to (a dropped commit, or load-bearing pre-existing dirt).
    (sandbox / "justfile").write_text(_justfile(gate_ci="    test -f marker.txt\n"))
    import subprocess

    subprocess.run(["git", "add", "justfile"], cwd=sandbox, capture_output=True)
    subprocess.run(
        ["git", "commit", "-qm", "add gate-ci"], cwd=sandbox, capture_output=True
    )
    # Present in the tree, never committed (baseline dirt, so not a scope violation).
    (sandbox / "marker.txt").write_text("present in the working tree only\n")
    write_tasks(
        sandbox,
        """
### T1 — A
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`

### CP-1 — CHECKPOINT : merge
- **trigger :** auto quand [T1] done
- **validator :** Owner
- **mode :** blocking
""",
    )
    approve(sandbox, "CP-1")
    r = run_orch(sandbox)
    assert r.returncode == 0, r.stdout + r.stderr
    ev = _gate_at(sandbox, "CP-1")
    assert ev.get("full_gate") == "green"  # working tree has the marker
    assert ev.get("head_gate") == "RED"  # HEAD does not → divergence caught
    # The Owner gets an actionable gate report.
    assert (sandbox / "work" / "feat" / ".runs" / "CP-1-gate.md").exists()
