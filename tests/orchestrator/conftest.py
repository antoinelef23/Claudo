"""Harnais de test de l'orchestrateur : sandbox git + shim `claude` déterministe.

Le shim remplace le vrai CLI claude via PATH. Il extrait l'ID de tâche du prompt
et exécute le scénario `$LAB_ROOT/.shim/<ID>.sh` s'il existe (sa sortie = réponse
de l'agent), sinon répond `STATUS: done` (ou `VERDICT: PASS` pour le reviewer).
La réponse est enveloppée dans le JSON `--output-format json` du vrai CLI.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ORCH = REPO / "scripts" / "orchestrate.py"

SHIM = """#!/usr/bin/env bash
# Shim claude pour les tests orchestrateur — déterministe, instantané.
[ -n "${LAB_ROOT:-}" ] && echo "$@" >> "$LAB_ROOT/.shim/argv.log"
PROMPT="$2"
ID=""
if echo "$PROMPT" | grep -q "agent reviewer"; then
  ID="REVIEW"
else
  ID=$(echo "$PROMPT" | grep -oE "la tâche (T[0-9]+|CP-[0-9]+)" | head -1 | awk '{print $3}')
fi
OUT="STATUS: done"
[ "$ID" = "REVIEW" ] && OUT="VERDICT: PASS"
if [ -n "$ID" ] && [ -f "$LAB_ROOT/.shim/$ID.sh" ]; then
  OUT=$(bash "$LAB_ROOT/.shim/$ID.sh")
fi
OUT="$OUT" python3 -c 'import json, os; print(json.dumps({"type": "result", "result": os.environ["OUT"], "session_id": "shim-session", "total_cost_usd": 0.001}))'
"""

MAKEFILE = """evals:
\t@if [ -f .evals_fail ]; then echo "EVALS ROUGES (stub)"; exit 1; fi
\t@echo "[stub] evals ok"
"""

SPEC = """---
artifact: spec
feature: feat
version: 1.0.0
status: validated
---

# Spec — feat (sandbox)

- **INV-1** — Le système MUST exister.
- **BHV-1** — Given/When/Then de test.
- EVAL-1 : eval de test.
"""


@pytest.fixture()
def sandbox(tmp_path: Path) -> Path:
    sb = tmp_path / "sb"
    (sb / "work" / "feat").mkdir(parents=True)
    (sb / "bin").mkdir()
    (sb / ".shim").mkdir()
    (sb / "Makefile").write_text(MAKEFILE)
    (sb / "work" / "feat" / "spec.md").write_text(SPEC)
    shim = sb / "bin" / "claude"
    shim.write_text(SHIM)
    shim.chmod(0o755)
    subprocess.run(["git", "init", "-q"], cwd=sb, check=True)
    subprocess.run(["git", "config", "user.email", "test@lab"], cwd=sb, check=True)
    subprocess.run(["git", "config", "user.name", "lab-test"], cwd=sb, check=True)
    subprocess.run(["git", "add", "-A"], cwd=sb, check=True)
    subprocess.run(["git", "commit", "-qm", "init sandbox"], cwd=sb, check=True)
    return sb


def run_orch(
    sandbox: Path,
    *flags: str,
    feature: str = "work/feat",
    env_extra: dict | None = None,
):
    env = {
        **os.environ,
        "LAB_ROOT": str(sandbox),
        "LAB_NO_NOTIFY": "1",
        "LAB_TASK_TIMEOUT": "60",
        "PATH": f"{sandbox / 'bin'}:{os.environ['PATH']}",
        **(env_extra or {}),
    }
    # Hermétique : ne pas hériter d'un LAB_APPROVALS_DIR ambiant (ex. image sandbox qui le fixe)
    # sauf si un test le fournit explicitement — sinon les jetons écrits par approve() (dans
    # feature/.approvals) ne seraient pas lus par l'orchestrateur.
    if not (env_extra and "LAB_APPROVALS_DIR" in env_extra):
        env.pop("LAB_APPROVALS_DIR", None)
    return subprocess.run(
        [sys.executable, str(ORCH), feature, *flags],
        cwd=sandbox,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def approve(sandbox: Path, cp: str, feature: str = "work/feat") -> None:
    d = sandbox / feature / ".approvals"
    d.mkdir(parents=True, exist_ok=True)
    (d / cp).write_text("approved_by=test\n")


def write_registry(sandbox: Path, toml: str) -> None:
    (sandbox / "models").mkdir(exist_ok=True)
    (sandbox / "models" / "registry.toml").write_text(toml)


def argv_log(sandbox: Path) -> str:
    p = sandbox / ".shim" / "argv.log"
    return p.read_text() if p.exists() else ""
