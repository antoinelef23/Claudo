"""Dependency guard (spec BHV-4, INV-3, EX-3) — allowlist-only, offline."""

from __future__ import annotations

import pytest

import dep_guard


def write(tmp_path, pyproject: str, allowlist: str):
    py = tmp_path / "pyproject.toml"
    py.write_text(pyproject, encoding="utf-8")
    al = tmp_path / "allow.txt"
    al.write_text(allowlist, encoding="utf-8")
    return ["--pyproject", str(py), "--allowlist", str(al)]


# ------------------------------------------------------------------ evals


@pytest.mark.eval
def test_ex3_hallucinated_dep_fails(tmp_path, capsys):
    args = write(
        tmp_path,
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["leftpad-utils>=1"]\n',
        "pytest\nruff\n",
    )
    assert dep_guard.main(args) == 1
    assert "leftpad-utils" in capsys.readouterr().out


@pytest.mark.eval
def test_allowlisted_deps_pass(tmp_path):
    args = write(
        tmp_path,
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["pytest"]\n'
        '[dependency-groups]\ndev = ["ruff"]\n',
        "# ok\npytest\nruff\n",
    )
    assert dep_guard.main(args) == 0


@pytest.mark.eval
def test_repo_pyproject_is_fully_allowlisted():
    # Integration: the real repo must pass its own gate, strict included
    assert dep_guard.main([]) == 0
    assert dep_guard.main(["--strict"]) == 0


@pytest.mark.eval
def test_orphan_entry_fails_only_in_strict(tmp_path, capsys):
    # EVAL-6 / BHV-4a: allowlist carries `ruff` but pyproject no longer declares it
    args = write(
        tmp_path,
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["pytest"]\n',
        "pytest\nruff\n",
    )
    assert dep_guard.main(args) == 0  # local path: warn only
    assert "ruff" in capsys.readouterr().out
    assert dep_guard.main([*args, "--strict"]) == 1  # CI path: exact mirror
    assert "ruff" in capsys.readouterr().out


@pytest.mark.eval
def test_exact_mirror_passes_in_strict(tmp_path):
    args = write(
        tmp_path,
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["pytest"]\n'
        '[dependency-groups]\ndev = ["ruff"]\n',
        "pytest\nruff\n",
    )
    assert dep_guard.main([*args, "--strict"]) == 0


# ------------------------------------------------------------------ unit


def test_pep503_normalization_matches(tmp_path):
    args = write(
        tmp_path,
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["Left_Pad.utils==1"]\n',
        "left-pad-utils\n",
    )
    assert dep_guard.main(args) == 0


def test_optional_dependencies_are_checked(tmp_path):
    args = write(
        tmp_path,
        '[project]\nname = "x"\nversion = "0"\ndependencies = []\n'
        '[project.optional-dependencies]\nweb = ["fastapi"]\n',
        "pytest\n",
    )
    assert dep_guard.main(args) == 1


def test_missing_pyproject_is_noop(tmp_path, capsys):
    assert dep_guard.main(["--pyproject", str(tmp_path / "none.toml")]) == 0
    assert "nothing to check" in capsys.readouterr().out
