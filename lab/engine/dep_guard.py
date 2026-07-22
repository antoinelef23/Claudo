#!/usr/bin/env python3
"""Dependency guard — hallucinated dependencies are the AI-specific supply-chain
failure (whitepaper: slopsquatting). Rule (work/sdlc-rework INV-3): every package
declared in pyproject.toml must appear in lab/engine/dep_allowlist.txt, the one
sanctioned home for dependency names — so adding a dependency forces an explicit,
human-reviewed allowlist line in the same commit. Same mechanism as
brand_denylist.txt, inverted.

Offline and deterministic (ADR-3): NO PyPI lookup — verifying the package exists
and is well-spelled is the human's job when allowlisting it.

`--strict` (BHV-4a, the gate-ci path) also fails on ORPHAN allowlist entries
(no matching declared dep): the allowlist is an exact human-validated mirror,
never a superset — a stale entry would let a later re-add skip human re-review.

Usage:  python3 lab/engine/dep_guard.py [--strict] [--pyproject PATH] [--allowlist PATH]
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

# PEP 503 normalization: runs of -_. collapse to -, lowercase.
_NORM = re.compile(r"[-_.]+")
# Leading package name of a PEP 508 requirement string.
_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalize(name: str) -> str:
    return _NORM.sub("-", name).lower().strip()


def declared_deps(pyproject: Path) -> set[str]:
    """Every dependency name declared anywhere in pyproject.toml."""
    data = tomllib.loads(pyproject.read_text("utf-8"))
    reqs: list[str] = list(data.get("project", {}).get("dependencies", []))
    for group in data.get("project", {}).get("optional-dependencies", {}).values():
        reqs += group
    for group in data.get("dependency-groups", {}).values():
        # PEP 735 groups may contain {include-group = ...} tables — names only here
        reqs += [r for r in group if isinstance(r, str)]
    names: set[str] = set()
    for r in reqs:
        m = _REQ_NAME.match(r)
        if m:
            names.add(normalize(m.group(1)))
    return names


def load_allowlist(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    names: set[str] = set()
    for line in path.read_text("utf-8").splitlines():
        term = line.split("#")[0].strip()
        if term:
            names.add(normalize(term))
    return names


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description="Every declared dep must be allowlisted")
    ap.add_argument("--pyproject", type=Path, default=root / "pyproject.toml")
    ap.add_argument(
        "--allowlist", type=Path, default=root / "lab" / "engine" / "dep_allowlist.txt"
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="also fail on orphan allowlist entries (BHV-4a, CI path)",
    )
    args = ap.parse_args(argv)

    if not args.pyproject.is_file():
        print("[deps] no pyproject.toml — nothing to check")
        return 0
    declared = declared_deps(args.pyproject)
    allowed = load_allowlist(args.allowlist)
    rc = 0
    for name in sorted(declared - allowed):
        print(
            f"⛔ dependency `{name}` absent from {args.allowlist.name} — "
            f"verify it on PyPI (exact spelling) then allowlist it in the same commit"
        )
        rc = 1
    for name in sorted(allowed - declared):
        if args.strict:
            print(
                f"⛔ allowlist entry `{name}` matches no declared dependency — "
                f"remove the stale line (a re-add must go through human review again)"
            )
            rc = 1
        else:
            print(f"⚠️  allowlist entry `{name}` matches no declared dependency")
    if rc == 0:
        print(
            "[deps] allowlist and declared dependencies are an exact mirror"
            if args.strict
            else "[deps] all declared dependencies are allowlisted"
        )
    return rc


if __name__ == "__main__":
    sys.exit(main())
