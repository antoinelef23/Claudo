"""Garde-fou fond/forme : la forme peut bouger librement, le fond ne change que par
amendement (bump de version). Tests directs sur extract_content / diff_content + git.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "content_guard", REPO / "scripts" / "content_guard.py"
)
cg = importlib.util.module_from_spec(spec)
sys.modules["content_guard"] = cg
spec.loader.exec_module(cg)


SPEC_LIST = """---
version: 1.0.0
---
## 2. Glossary
| Terme | Nom canonique | Définition |
|---|---|---|
| Devis | `quote` | estimation |

## 3. Invariants
- **INV-1** — Le total MUST être ≥ 0.
- **INV-2** — `is_estimate` MUST valoir True.

## 4. Behaviors
### BHV-1 — pose
- **Given** une surface > 0
- **Then** pose = surface × 45.0
"""

# MÊME FOND, forme différente : table au lieu de liste, gras déplacé, sections réordonnées
SPEC_TABLE = """---
version: 1.0.0
---
## 4. Behaviors

### BHV-1 — pose
**Given** une surface > 0 **Then** pose = surface × 45.0

## 3. Invariants

| ID | Règle |
|---|---|
| INV-1 | Le total MUST être ≥ 0. |
| INV-2 | `is_estimate` MUST valoir True. |

## 2. Glossary
- Devis (`quote`) : estimation
"""


def test_form_change_preserves_content():
    assert cg.diff_content(SPEC_LIST, SPEC_TABLE) == {}, cg.diff_content(
        SPEC_LIST, SPEC_TABLE
    )


def test_changed_invariant_is_detected():
    altered = SPEC_LIST.replace("MUST être ≥ 0", "MUST être > 0")
    changed = cg.diff_content(SPEC_LIST, altered)
    assert "INV-1" in changed


def test_changed_behavior_value_is_detected():
    altered = SPEC_LIST.replace("× 45.0", "× 50.0")
    changed = cg.diff_content(SPEC_LIST, altered)
    assert "BHV-1" in changed


def test_changed_glossary_canonical_name_is_detected():
    altered = SPEC_LIST.replace("`quote`", "`devis_obj`")
    changed = cg.diff_content(SPEC_LIST, altered)
    assert any(k.startswith("GLOSS:") for k in changed)


def _git(wd, *a):
    subprocess.run(
        ["git", *a],
        cwd=wd,
        capture_output=True,
        check=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@x",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@x",
            "PATH": __import__("os").environ["PATH"],
        },
    )


def _run_guard(wd, path):
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / "content_guard.py"), "--git", path],
        cwd=wd,
        capture_output=True,
        text=True,
    )


def test_git_reformat_ok_but_content_change_blocked(tmp_path):
    wd = tmp_path / "r"
    (wd / "work").mkdir(parents=True)
    f = wd / "work" / "spec.md"
    f.write_text(SPEC_LIST)
    _git(wd, "init", "-q")
    _git(wd, "add", "-A")
    _git(wd, "commit", "-qm", "v1")

    # reformat pur (table) → fond identique → exit 0
    f.write_text(SPEC_TABLE)
    r = _run_guard(wd, "work/spec.md")
    assert r.returncode == 0, r.stdout

    # changement de fond SANS bump de version → exit 1
    f.write_text(SPEC_LIST.replace("× 45.0", "× 50.0"))
    r = _run_guard(wd, "work/spec.md")
    assert r.returncode == 1, r.stdout
    assert "FOND a changé SANS bump" in r.stdout

    # même changement AVEC bump de version (amendement) → exit 0
    f.write_text(
        SPEC_LIST.replace("× 45.0", "× 50.0").replace(
            "version: 1.0.0", "version: 1.1.0"
        )
    )
    r = _run_guard(wd, "work/spec.md")
    assert r.returncode == 0, r.stdout
