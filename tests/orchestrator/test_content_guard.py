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


# ----------------------------------------------------- durcissement (revue 2026-06-15)


def test_changed_glossary_definition_is_detected():
    # H6 — modifier la DÉFINITION d'un terme (pas seulement son nom canonique) est du fond
    altered = SPEC_LIST.replace(
        "| `quote` | estimation |", "| `quote` | facture ferme |"
    )
    changed = cg.diff_content(SPEC_LIST, altered)
    assert any(k.startswith("GLOSS:") for k in changed), changed


DESIGN_SIG = """---
version: 1.0.0
---
## 5. Contracts & data

```python
def price(cart: dict, coupons: list, context: dict) -> dict: ...
```
"""


def test_design_codeblock_is_fingerprinted():
    # H5 — une signature dans un bloc de code (hors ADR) est du fond : la changer est détecté
    altered = DESIGN_SIG.replace("-> dict", "-> float")
    changed = cg.diff_content(DESIGN_SIG, altered)
    assert any(k.startswith("CODE:") for k in changed), changed


def test_design_codeblock_reformat_is_invisible():
    # …mais un simple reformat (indentation, espaces) ne touche pas le fond
    altered = DESIGN_SIG.replace(
        "def price(cart: dict, coupons: list, context: dict) -> dict: ...",
        "def price(cart: dict, coupons: list, context: dict) -> dict:\n    ...",
    )
    # le découpage en deux lignes garde les mêmes tokens normalisés → pas de changement de fond
    changed = cg.diff_content(DESIGN_SIG, altered)
    assert changed == {}, changed


def test_git_downgrade_does_not_authorize_fond_change(tmp_path):
    # M6 — un fond modifié avec une version NON croissante (downgrade) reste bloqué
    wd = tmp_path / "rd"
    (wd / "work").mkdir(parents=True)
    f = wd / "work" / "spec.md"
    f.write_text(SPEC_LIST)  # version 1.0.0
    _git(wd, "init", "-q")
    _git(wd, "add", "-A")
    _git(wd, "commit", "-qm", "v1")
    f.write_text(
        SPEC_LIST.replace("× 45.0", "× 50.0").replace(
            "version: 1.0.0", "version: 0.9.0"
        )
    )
    r = _run_guard(wd, "work/spec.md")
    assert r.returncode == 1, r.stdout
    assert "NON croissante" in r.stdout


# --------------------------------------- 2e passe : corrige les régressions H5/H6/M6 (revue n°2)

GLOSS_REF = """---
version: 1.0.0
---
## 2. Glossary
| Terme | Code | Définition |
|---|---|---|
| Part | `parts` | nombre de beneficiaires |
| Repartition | `shares` | liste de `parts` entiers dont la somme vaut le total |
"""


def test_glossary_inline_reference_does_not_shadow_definition():
    # H6 (régression) — le row `shares` mentionne `parts` inline ; changer la définition PROPRE
    # de `parts` doit rester détecté (la mention inline ne doit pas écraser GLOSS:parts).
    altered = GLOSS_REF.replace(
        "nombre de beneficiaires", "nombre total de parts egales"
    )
    changed = cg.diff_content(GLOSS_REF, altered)
    assert "GLOSS:parts" in changed, changed


DESIGN_MERMAID = """---
version: 1.0.0
---
## 1. Architecture

```mermaid
flowchart LR
    A --> B
```
"""


def test_mermaid_reformat_is_invisible():
    # H5 (régression) — un diagramme est de la FORME : le re-layout ne doit pas exiger un bump
    altered = DESIGN_MERMAID.replace(
        "flowchart LR\n    A --> B", "flowchart TD\n    A --> B\n    B --> A"
    )
    changed = cg.diff_content(DESIGN_MERMAID, altered)
    assert changed == {}, changed


DESIGN_TWO = """---
version: 1.0.0
---
## 3. Stack

```python
X = 1
```

## 5. Contracts

```python
def f() -> int: ...
```
"""


def test_code_block_keys_are_section_anchored():
    # H5 (régression) — ajouter un bloc dans une section ne doit faire apparaître QUE cette
    # section comme changée (clés ancrées à la section, pas un index positionnel global).
    altered = DESIGN_TWO.replace(
        "## 3. Stack\n\n```python\nX = 1\n```",
        "## 3. Stack\n\n```python\nX = 1\n```\n\n```python\nY = 2\n```",
    )
    changed = cg.diff_content(DESIGN_TWO, altered)
    assert set(changed) == {"CODE:3. Stack"}, changed


def test_git_version_extra_component_not_a_bump(tmp_path):
    # M6 (régression) — `1.0.0` → `1.0.0.0` n'est PAS un bump (semver strict 3 composants)
    wd = tmp_path / "rx"
    (wd / "work").mkdir(parents=True)
    f = wd / "work" / "spec.md"
    f.write_text(SPEC_LIST)
    _git(wd, "init", "-q")
    _git(wd, "add", "-A")
    _git(wd, "commit", "-qm", "v1")
    f.write_text(
        SPEC_LIST.replace("× 45.0", "× 50.0").replace(
            "version: 1.0.0", "version: 1.0.0.0"
        )
    )
    r = _run_guard(wd, "work/spec.md")
    assert r.returncode == 1, r.stdout
