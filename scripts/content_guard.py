#!/usr/bin/env python3
"""Garde-fou FOND vs FORME pour spec.md et design.md.

Principe : le **fond** (le contrat métier de la spec, l'image technique du design) ne
change QUE par amendement humain explicite (bump de version). La **forme** (mise en page,
table↔liste, gras, ordre des sections, reformulation de prose) peut évoluer librement —
notamment pour qu'un autre modèle comprenne mieux — MAIS sans jamais altérer le fond.

Ce script rend la règle mécanique : il extrait une **empreinte de fond** robuste à la forme
et refuse tout changement de fond qui ne s'accompagne pas d'un bump de version.

L'empreinte = contenu STRUCTURÉ et testable, normalisé (formatage retiré) :
  - les assertions par ID : INV / BHV / EX / EVAL / NG / OQ (spec) et ADR (design),
    avec leurs lignes de continuation (Given/When/Then, YAML d'exemple, décision d'ADR) ;
  - les noms canoniques du glossaire (le code DOIT les utiliser → c'est du fond) ;
  - les lignes KPI (valeurs chiffrées = fond).
La prose libre (intent, commentaires) n'est PAS dans l'empreinte : sa reformulation est de la forme.

Usage :
  content_guard.py <ancien.md> <nouveau.md>      # compare deux fichiers
  content_guard.py --git work/feat/spec.md        # compare l'arbre de travail à HEAD
                                                   # exit 1 si le fond change sans bump de version
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ID = r"(?:INV|BHV|EX|EVAL|NG|OQ|ADR)-\w+"
_LEADING = re.compile(r"^[\s#\-*|`>]+")
_DEF = re.compile(rf"^\*{{0,2}}({ID})")
_HEAD2 = re.compile(r"^#{1,2}\s")  # ## section → reset du contexte d'ID
_KPI = re.compile(r"KPI", re.I)
_FMT = re.compile(r"[`*_#>|]")


def _norm(s: str) -> str:
    """Normalise une ligne : retire le formatage markdown (gras, table, puces,
    séparateurs em-dash) pour que liste↔table↔prose donnent le même fond."""
    s = _FMT.sub(" ", s)  # ` * _ # > |
    s = re.sub(r"^\s*[-*]\s+", " ", s)  # puce de liste en tête
    s = re.sub(r"\s+[—–-]\s+", " ", s)  # séparateurs « — » / « – » / « - » espacés
    return re.sub(r"\s+", " ", s).strip()


def extract_content(text: str) -> dict[str, str]:
    """Empreinte de fond : {clé -> texte normalisé}. Robuste à la forme."""
    content: dict[str, list[str]] = {}
    current: str | None = None
    in_glossary = False

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = _LEADING.sub("", line)
        m = _DEF.match(stripped)
        if m:  # une ligne qui INTRODUIT un ID (def, pas mention inline)
            current = m.group(1)
            content.setdefault(current, []).append(_norm(line))
            continue
        if _HEAD2.match(line):  # frontière de section
            current = None
            in_glossary = (
                "gloss—" in line.lower()
                or "glossary" in line.lower()
                or "glossaire" in line.lower()
            )
            continue
        # lignes de continuation rattachées à l'ID courant (Given/When/Then, YAML, ADR…)
        if current and line.strip():
            content[current].append(_norm(line))
            continue
        # glossaire : noms canoniques (code), quelle que soit la forme (table OU liste)
        if in_glossary:
            for c in re.findall(r"`([^`]+)`", line):
                content[f"GLOSS:{c}"] = [c]
        # lignes KPI hors ID
        if _KPI.search(line):
            content.setdefault("KPI", []).append(_norm(line))

    return {k: " ".join(v) for k, v in content.items()}


def diff_content(old: str, new: str) -> dict[str, tuple[str, str]]:
    """Renvoie {clé -> (avant, après)} pour chaque élément de fond modifié/ajouté/supprimé."""
    a, b = extract_content(old), extract_content(new)
    changed: dict[str, tuple[str, str]] = {}
    for k in sorted(set(a) | set(b)):
        if a.get(k, "") != b.get(k, ""):
            changed[k] = (a.get(k, "∅"), b.get(k, "∅"))
    return changed


def _version(text: str) -> str | None:
    m = re.search(r"^version:\s*([\w.\-]+)", text, re.M)
    return m.group(1) if m else None


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--git":
        path = args[1]
        new = Path(path).read_text(encoding="utf-8")
        try:
            rel = (
                subprocess.run(
                    ["git", "ls-files", "--full-name", path],
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                or path
            )
            old = subprocess.run(
                ["git", "show", f"HEAD:{rel}"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        except subprocess.CalledProcessError:
            print(f"✅ {path} : nouveau fichier (pas de version HEAD à comparer)")
            return 0
    elif len(args) == 2:
        old = Path(args[0]).read_text(encoding="utf-8")
        new = Path(args[1]).read_text(encoding="utf-8")
        path = args[1]
    else:
        print(__doc__)
        return 2

    changed = diff_content(old, new)
    if not changed:
        print(f"✅ {path} : fond identique — la forme peut évoluer librement.")
        return 0

    bumped = _version(old) != _version(new)
    print(
        f"{'✅' if bumped else '⛔'} {path} : {len(changed)} élément(s) de fond modifié(s) :"
    )
    for k, (av, ap) in changed.items():
        print(f"  • {k}\n      avant : {av[:120]}\n      après : {ap[:120]}")
    if bumped:
        print(
            f"→ version bumpée ({_version(old)} → {_version(new)}) : amendement assumé, OK."
        )
        return 0
    print(
        "→ ⛔ le FOND a changé SANS bump de version. Un reformat ne doit toucher que la FORME.\n"
        "  Si c'est volontaire (amendement métier/technique), bumpe `version:` + changelog\n"
        "  (commit séparé). Sinon, restaure le fond et ne garde que la mise en forme."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
