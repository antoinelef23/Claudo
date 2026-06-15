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


def _norm_gloss(s: str) -> str:
    """Normalisation agressive pour le glossaire : ne garde que les mots (lettres/chiffres,
    accents et `_` compris), en minuscules. Rend la DÉFINITION d'un terme robuste à la forme
    (table | liste | prose, ponctuation, parenthèses) tout en capturant son SENS — pas
    seulement le nom canonique (H6 : sinon on peut inverser la définition d'un terme sans diff)."""
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip().lower()


def extract_content(text: str) -> dict[str, str]:
    """Empreinte de fond : {clé -> texte normalisé}. Robuste à la forme."""
    content: dict[str, list[str]] = {}
    current: str | None = None
    in_glossary = False
    in_code = False
    code_idx = 0

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):  # frontière de bloc de code clôturé
            in_code = not in_code
            if in_code and current is None:
                code_idx += (
                    1  # nouveau bloc HORS ID (ex. design §5 signatures, §1 diagramme)
                )
            continue
        if in_code:
            # H5 — contenu d'un bloc clôturé : sous un ID (EX/ADR) → continuation de cet ID ;
            # sinon → CODE:n (signatures/contrats du design, jusqu'ici jamais empreintés).
            if line.strip():
                key = current if current is not None else f"CODE:{code_idx}"
                content.setdefault(key, []).append(_norm(line))
            continue
        stripped = _LEADING.sub("", line)
        m = _DEF.match(stripped)
        if m:  # une ligne qui INTRODUIT un ID (def, pas mention inline)
            current = m.group(1)
            content.setdefault(current, []).append(_norm(line))
            continue
        if _HEAD2.match(line):  # frontière de section
            current = None
            low = line.lower()
            in_glossary = "glossary" in low or "glossaire" in low
            continue
        # lignes de continuation rattachées à l'ID courant (Given/When/Then, YAML, ADR…)
        if current and line.strip():
            content[current].append(_norm(line))
            continue
        # glossaire : une clé par nom canonique, valeur = ligne ENTIÈRE (nom + définition)
        # normalisée agressivement → robuste à la forme, sensible au sens (H6).
        if in_glossary:
            for c in re.findall(r"`([^`]+)`", line):
                content[f"GLOSS:{c}"] = [_norm_gloss(line)]
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


def _ver_tuple(v: str | None) -> tuple[int, ...] | None:
    if not v:
        return None
    parts = re.findall(r"\d+", v)
    return tuple(int(x) for x in parts) if parts else None


def _focus(a: str, b: str, ctx: int = 25, tail: int = 70) -> tuple[str, str]:
    """Cadre l'aperçu autour de la PREMIÈRE divergence (sinon une diff loin
    dans une longue ligne reste invisible — les deux côtés paraissent identiques)."""
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    start = max(0, i - ctx)
    pre = "…" if start > 0 else ""

    def cut(s: str) -> str:
        end = i + tail
        return pre + s[start:end] + ("…" if end < len(s) else "")

    return cut(a), cut(b)


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

    ov, nv = _version(old), _version(new)
    ot, nt = _ver_tuple(ov), _ver_tuple(nv)
    # M6 — un amendement = un bump STRICTEMENT croissant. Un downgrade, une valeur égale ou
    # malformée ne suffit pas (sinon « touche la ligne version: » défait la garde).
    bumped = ot is not None and nt is not None and nt > ot
    print(
        f"{'✅' if bumped else '⛔'} {path} : {len(changed)} élément(s) de fond modifié(s) :"
    )
    for k, (av, ap) in changed.items():
        fa, fb = _focus(av, ap)
        print(f"  • {k}\n      avant : {fa}\n      après : {fb}")
    if bumped:
        print(f"→ version bumpée ({ov} → {nv}) : amendement assumé, OK.")
        return 0
    if ot is not None and nt is not None and nt <= ot and ov != nv:
        print(
            f"→ ⛔ version NON croissante ({ov} → {nv}) : un amendement exige un bump strictement\n"
            "  supérieur. Un downgrade n'autorise pas un changement de fond."
        )
        return 1
    print(
        "→ ⛔ le FOND a changé SANS bump de version. Un reformat ne doit toucher que la FORME.\n"
        "  Si c'est volontaire (amendement métier/technique), bumpe `version:` + changelog\n"
        "  (commit séparé). Sinon, restaure le fond et ne garde que la mise en forme."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
