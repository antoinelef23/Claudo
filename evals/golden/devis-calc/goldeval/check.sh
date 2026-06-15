#!/usr/bin/env bash
# Verdict LOGIQUE (nom-agnostique) : un callable QUELCONQUE du répertoire calcule-t-il
# correctement ? Indépendant du nom de fichier/fonction (ça, c'est le verdict API séparé).
set -uo pipefail
python3 - <<'PY'
import sys, importlib.util, pathlib, inspect
sys.path.insert(0, ".")

def funcs():
    out = []
    for p in pathlib.Path(".").rglob("*.py"):
        if "goldeval" in p.parts:
            continue
        try:
            s = importlib.util.spec_from_file_location(p.stem, p)
            m = importlib.util.module_from_spec(s)
            s.loader.exec_module(m)
        except Exception:
            continue
        out += [f for _, f in inspect.getmembers(m, inspect.isfunction)]
    return out

def approx(a, b): return abs(float(a) - b) < 0.01

cases = [
    ((1500, 10), {"products_eur": 1500.0, "installation_eur": 450.0, "total_eur": 1950.0}),
    ((2500, 20), {"products_eur": 2375.0, "installation_eur": 900.0, "total_eur": 3275.0}),
    ((100, 0), {"total_eur": 100.0}),
]

def works(fn):
    try:
        for args, exp in cases:
            r = fn(*args)
            for k, v in exp.items():
                if not approx(r[k], v):
                    return False
        return float(fn(-100, -5)["total_eur"]) >= 0  # INV-1 clamp
    except Exception:
        return False

ok = any(works(f) for f in funcs())
print("logic OK" if ok else "logic FAIL : aucun callable ne calcule correctement")
sys.exit(0 if ok else 1)
PY
