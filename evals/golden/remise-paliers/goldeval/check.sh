#!/usr/bin/env bash
# Verdict LOGIQUE (nom-agnostique) : un callable QUELCONQUE calcule-t-il les paliers + clamp ?
# Indépendant du nom de fichier/fonction (verdict API séparé). Teste la logique, pas le contrat.
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
    ((1000, 0), {"products_eur": 1000.00}),     # borne basse : 0 %
    ((1000.01, 0), {"products_eur": 950.01}),    # juste au-dessus : 5 %
    ((5000, 10), {"products_eur": 4750.00, "installation_eur": 450.00}),  # borne haute 5 % inclusive
    ((5000.01, 0), {"products_eur": 4500.01}),   # juste au-dessus : 10 %
]

def works(fn):
    try:
        for args, exp in cases:
            r = fn(*args)
            for k, v in exp.items():
                if not approx(r[k], v):
                    return False
        return float(fn(-100, -5)["total_eur"]) == 0.0  # clamp INV-1
    except Exception:
        return False

ok = any(works(f) for f in funcs())
print("logic OK" if ok else "logic FAIL : aucun callable ne calcule les paliers correctement")
sys.exit(0 if ok else 1)
PY
