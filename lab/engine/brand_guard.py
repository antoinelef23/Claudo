#!/usr/bin/env python3
"""Brand / proper-noun guard — keeps the lab generic / org-neutral.

The hard rule (CLAUDE.md): no client or brand proper nouns committed in the
FRAMEWORK content. This makes it mechanical — a deterministic denylist
(lab/engine/brand_denylist.txt) scanned over the committed lab content.

SCOPE — the rule applies to the lab ITSELF, not to its usage a posteriori:
  - `work/**` (real features built with the lab) and `**/assets/**` (raw client
    inputs: transcripts, slides, quotes) legitimately contain brand names and are
    EXCLUDED from the scan.
  - The denylist file is the one sanctioned home for the names and is excluded too.

NOTE: lab spec-ID prefixes (INV / BHV / EX / EVAL / NG / OQ / ADR) are vocabulary,
never brands — they must never appear in the denylist.

Usage:
  brand_guard.py --all                 # scan all tracked in-scope files (CI gate)
  brand_guard.py --staged              # scan staged in-scope files (pre-commit)
  brand_guard.py FILE [FILE ...]       # scan explicit files
Exit 1 on any hit (prints file:line + matched term), 0 if clean.

LAB_BRAND_DENYLIST overrides the denylist path (tests).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

DENYLIST_PATH = Path(
    os.environ.get("LAB_BRAND_DENYLIST")
    or (Path(__file__).resolve().parent / "brand_denylist.txt")
)

# Excluded from the scan: usage a posteriori + non-source + the detector's own config.
EXCLUDE_PREFIXES = ("work/", "assets/")
EXCLUDE_SUBSTR = ("/assets/",)
EXCLUDE_NAMES = {"brand_denylist.txt", "sbom.json", "uv.lock"}
EXCLUDE_SUFFIX = (
    ".jsonl",
    ".lock",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".pdf",
    ".pptx",
    ".woff",
    ".woff2",
    ".ico",
)


def load_denylist(path: Path = DENYLIST_PATH) -> list[tuple[str, re.Pattern[str]]]:
    """Parse the denylist: one term per line, `#` comments, blank lines ignored.
    Each term -> a word-boundary, case-insensitive pattern."""
    terms: list[tuple[str, re.Pattern[str]]] = []
    if not path.exists():
        return terms
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        terms.append((line, re.compile(rf"\b{re.escape(line)}\b", re.IGNORECASE)))
    return terms


def in_scope(rel: str) -> bool:
    """A repo-relative path is in scope unless it is usage a posteriori, the
    detector's config, or a non-text/data file."""
    if any(rel.startswith(p) for p in EXCLUDE_PREFIXES):
        return False
    if any(s in rel for s in EXCLUDE_SUBSTR):
        return False
    if Path(rel).name in EXCLUDE_NAMES:
        return False
    if rel.endswith(EXCLUDE_SUFFIX):
        return False
    return True


def _git(args: list[str]) -> list[str]:
    out = subprocess.run(["git", *args], capture_output=True, text=True)
    return [line for line in out.stdout.splitlines() if line]


def scan_file(
    rel: str, terms: list[tuple[str, re.Pattern[str]]]
) -> list[tuple[int, str, str]]:
    """Return (lineno, term, line) for every denylist hit in the file. Binary or
    unreadable files yield nothing."""
    try:
        text = Path(rel).read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError, OSError):
        return []
    hits: list[tuple[int, str, str]] = []
    for i, line in enumerate(text.splitlines(), 1):
        for term, pat in terms:
            if pat.search(line):
                hits.append((i, term, line.strip()))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="Brand/proper-noun guard for the lab.")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument(
        "--all", action="store_true", help="scan all tracked in-scope files"
    )
    grp.add_argument("--staged", action="store_true", help="scan staged in-scope files")
    ap.add_argument("files", nargs="*", help="explicit files to scan")
    args = ap.parse_args()

    terms = load_denylist()
    if not terms:
        print(f"ℹ️  brand_guard: empty denylist ({DENYLIST_PATH}) — nothing to enforce.")
        return 0

    if args.all:
        candidates = _git(["ls-files"])
    elif args.staged:
        candidates = _git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    else:
        candidates = args.files
    targets = [f for f in candidates if in_scope(f)]

    total = 0
    for rel in targets:
        for ln, term, line in scan_file(rel, terms):
            print(f"⛔ {rel}:{ln}: brand/proper noun '{term}' — {line}")
            total += 1

    if total:
        print(
            f"\n⛔ brand_guard: {total} forbidden brand reference(s). The lab stays "
            "generic/org-neutral.\n"
            "   Real features go under work/ (excluded), raw client inputs under assets/ "
            "(excluded).\n"
            "   If a term is legitimate lab content, fix the text — do NOT add it to the denylist."
        )
        return 1

    scope = (
        "all tracked"
        if args.all
        else ("staged" if args.staged else f"{len(targets)} file(s)")
    )
    print(f"✅ brand_guard: clean ({scope} in-scope, {len(terms)} denied terms).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
