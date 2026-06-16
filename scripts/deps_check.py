#!/usr/bin/env python3
"""Anti-slopsquatting (OWASP LLM09) : vérifie que chaque dépendance DÉCLARÉE existe vraiment
sur PyPI. Un agent qui code peut halluciner un nom de paquet ; un attaquant enregistre ce nom
→ install d'un paquet malveillant. `pip-audit` ne voit que les CVE de paquets RÉELS ; lui ne
verrait pas un nom inexistant/fraîchement squatté. Ce garde-fou ferme l'angle.

Politique :
  - paquet introuvable sur PyPI (HTTP 404)            → ÉCHEC (exit 1) : nom suspect.
  - réseau indisponible / erreur transitoire          → WARN, exit 0 : on ne bloque pas hors-ligne.
Lit les dépendances de pyproject.toml ([project.dependencies] + [dependency-groups]).
"""

from __future__ import annotations

import re
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# nom de paquet en tête d'un spécificateur PEP 508 (avant version/extras/marqueurs)
_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def declared_deps(pyproject: Path) -> set[str]:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    specs: list[str] = list(data.get("project", {}).get("dependencies", []) or [])
    for group in (data.get("dependency-groups", {}) or {}).values():
        specs += [g for g in group if isinstance(g, str)]
    names = set()
    for s in specs:
        m = _NAME.match(s.strip())
        if m:
            names.add(m.group(1).lower())
    return names


def exists_on_pypi(name: str) -> bool | None:
    """True/False si on a pu trancher ; None si réseau indisponible (on ne bloque pas)."""
    url = f"https://pypi.org/pypi/{name}/json"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:  # nosec B310 — https constant, nom validé
            return r.status == 200
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        return None  # 5xx/403 transitoire : indéterminé
    except (urllib.error.URLError, TimeoutError, OSError):
        return None  # hors-ligne : ne pas bloquer


def main() -> int:
    pyproject = ROOT / "pyproject.toml"
    if not pyproject.exists():
        print("[deps-check] pas de pyproject.toml — skip")
        return 0
    deps = sorted(declared_deps(pyproject))
    if not deps:
        print("[deps-check] aucune dépendance déclarée — rien à vérifier")
        return 0
    missing, unknown = [], []
    for name in deps:
        res = exists_on_pypi(name)
        if res is False:
            missing.append(name)
        elif res is None:
            unknown.append(name)
    if unknown:
        print(
            f"⚠️  [deps-check] réseau indisponible pour {len(unknown)} paquet(s) — non vérifiés : {', '.join(unknown)}"
        )
    if missing:
        print(
            f"❌ [deps-check] dépendance(s) INTROUVABLE(S) sur PyPI (slopsquatting ?) : {', '.join(missing)}"
        )
        return 1
    print(
        f"✅ [deps-check] {len(deps) - len(unknown)} dépendance(s) vérifiée(s) sur PyPI"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
