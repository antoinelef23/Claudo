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


# ----------------------------------------------------- M1 : listes numérotées


def test_numbered_list_ids_are_captured():
    # finding M1 : « 1. **INV-1** … » doit voir son ID capté dans l'empreinte.
    numbered = """---
version: 1.0.0
---
## 3. Invariants
1. **INV-1** — Le total MUST être ≥ 0.
2. **INV-2** — `is_estimate` MUST valoir True.
"""
    content = cg.extract_content(numbered)
    assert "INV-1" in content and "INV-2" in content


def test_bullet_to_numbered_is_form_only():
    # Reformater puce → numéro est de la FORME : aucun changement de fond.
    bullet = "---\nversion: 1.0.0\n---\n## Inv\n- **INV-1** — total ≥ 0\n"
    numbered = "---\nversion: 1.0.0\n---\n## Inv\n1. **INV-1** — total ≥ 0\n"
    assert cg.diff_content(bullet, numbered) == {}


def test_substance_change_in_numbered_list_is_detected():
    # Le fond change dans une liste numérotée → détecté (avant M1 : invisible).
    a = "---\nversion: 1.0.0\n---\n## Inv\n1. **INV-1** — total ≥ 0\n"
    b = "---\nversion: 1.0.0\n---\n## Inv\n1. **INV-1** — total ≥ 100\n"
    assert "INV-1" in cg.diff_content(a, b)


# ----------------------------------------------------- L2 : trait d'union opérateur


def test_operator_hyphen_drop_is_detected():
    # finding L2 : « price - discount » → « price discount » = changement de fond.
    with_op = (
        "---\nversion: 1.0.0\n---\n## Inv\n- **INV-1** — cost = price - discount\n"
    )
    without = "---\nversion: 1.0.0\n---\n## Inv\n- **INV-1** — cost = price discount\n"
    assert "INV-1" in cg.diff_content(with_op, without)


def test_typographic_dash_separator_is_still_form():
    # Le tiret typographique « — » reste un séparateur de forme (normalisé).
    a = "---\nversion: 1.0.0\n---\n## Inv\n- **INV-1** — total ≥ 0\n"
    b = "---\nversion: 1.0.0\n---\n## Inv\n- **INV-1**   total ≥ 0\n"
    assert cg.diff_content(a, b) == {}


def test_inline_id_crossref_is_not_a_definition():
    # Un design.md qui RÉFÉRENCE un ID inline (sans le définir) reste valide : son fond
    # n'est pas empreinté par cet ID, et un reformat de la prose ne déclenche rien.
    a = "---\nversion: 1.0.0\n---\n# Design\nRéutilise le socle (ADR-1 : fonctions pures).\n"
    b = "---\nversion: 1.0.0\n---\n# Design\nS'appuie sur le socle (ADR-1 : fonctions pures).\n"
    assert cg.diff_content(a, b) == {}  # prose libre = forme


# ----------------------------------------------------- M11 : --against <ref> (CI)


def test_against_ref_detects_change_vs_base(tmp_path):
    # finding M11 : --against compare l'arbre de travail à une BASE arbitraire (pas HEAD)
    # — c'est le seul mode utile en CI (en checkout propre, arbre==HEAD).
    wd = tmp_path / "r"
    (wd / "work").mkdir(parents=True)
    f = wd / "work" / "spec.md"
    f.write_text(SPEC_LIST)
    _git(wd, "init", "-q")
    _git(wd, "add", "-A")
    _git(wd, "commit", "-qm", "v1")
    _git(wd, "branch", "base")

    # même contenu que base → pas de changement (le mode --against fonctionne hors HEAD)
    r = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "content_guard.py"),
            "--against",
            "base",
            "work/spec.md",
        ],
        cwd=wd,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout

    # change le fond sans bump → détecté vs base
    f.write_text(SPEC_LIST.replace("× 45.0", "× 99.0"))
    r = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "content_guard.py"),
            "--against",
            "base",
            "work/spec.md",
        ],
        cwd=wd,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1, r.stdout
    assert "FOND a changé SANS bump" in r.stdout


def test_ci_checks_blocks_fond_change_without_bump(tmp_path):
    # finding M11/L5 : ci_checks.sh découvre les features changées vs BASE et bloque un
    # changement de fond sans bump ; le bump le débloque.
    import os
    import shutil

    wd = tmp_path / "r"
    wd.mkdir()
    shutil.copytree(REPO / "scripts", wd / "scripts")
    shutil.copy(REPO / "Makefile", wd / "Makefile")
    (wd / "work" / "feat").mkdir(parents=True)
    (wd / "work" / "feat" / "spec.md").write_text(SPEC_LIST)
    # -b base : branche initiale déterministe (sinon « main » en local mais « master »
    # sur le git d'Ubuntu CI → la base serait introuvable et le skip fail-safe ferait
    # passer le test à tort).
    _git(wd, "init", "-q", "-b", "base")
    _git(wd, "add", "-A")
    _git(wd, "commit", "-qm", "base")
    _git(wd, "checkout", "-q", "-b", "feature")
    (wd / "work" / "feat" / "spec.md").write_text(SPEC_LIST.replace("× 45.0", "× 99.0"))
    _git(wd, "commit", "-qam", "sneaky")

    env = {**os.environ, "BASE": "base"}
    r = subprocess.run(
        ["bash", "scripts/ci_checks.sh"],
        cwd=wd,
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1, r.stdout + r.stderr
    assert "work/feat" in r.stdout

    # bump → débloque
    (wd / "work" / "feat" / "spec.md").write_text(
        SPEC_LIST.replace("× 45.0", "× 99.0").replace(
            "version: 1.0.0", "version: 1.1.0"
        )
    )
    _git(wd, "commit", "-qam", "bump")
    r2 = subprocess.run(
        ["bash", "scripts/ci_checks.sh"],
        cwd=wd,
        env=env,
        capture_output=True,
        text=True,
    )
    assert r2.returncode == 0, r2.stdout + r2.stderr
