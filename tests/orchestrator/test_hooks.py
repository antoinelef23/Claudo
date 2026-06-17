"""Régression du hook eval_gate.sh — findings H7/H8 (gate d'evals interactif)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .conftest import REPO

HOOK = REPO / "scripts" / "hooks" / "eval_gate.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_eval_gate_sees_new_untracked_package_dir(tmp_path: Path) -> None:
    # finding H7 : un module neuf non suivi s'affiche `?? newpkg/` (une seule ligne) ;
    # sans --untracked-files=all le grep le rate et le gate SAUTE. Ici les evals sont
    # rouges : le gate corrigé DOIT tourner et sortir 2 (pas sauter en 0).
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname = 'x'\nversion = '0'\n")
    (repo / "Makefile").write_text("evals:\n\t@echo 'EVALS RED'; exit 1\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@lab")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")

    # Feature livrée comme NOUVEAU package non suivi.
    (repo / "newpkg").mkdir()
    (repo / "newpkg" / "mod.py").write_text("x = 1\n")

    r = subprocess.run(
        ["bash", str(HOOK)], cwd=repo, input="{}", text=True, capture_output=True
    )
    assert r.returncode == 2, (
        f"le gate devrait TOURNER (rouge) sur un module neuf non suivi, "
        f"pas sauter ; rc={r.returncode}\n{r.stdout}{r.stderr}"
    )
    assert "EVAL GATE ROUGE" in r.stderr


def test_eval_gate_skips_when_no_code_changed(tmp_path: Path) -> None:
    # Sanity : sans changement de code, le gate ne paie pas les evals (exit 0).
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname = 'x'\nversion = '0'\n")
    (repo / "Makefile").write_text("evals:\n\t@echo 'EVALS RED'; exit 1\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@lab")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")

    r = subprocess.run(
        ["bash", str(HOOK)], cwd=repo, input="{}", text=True, capture_output=True
    )
    assert r.returncode == 0, f"rien n'a changé → pas de gate ; {r.stderr}"
