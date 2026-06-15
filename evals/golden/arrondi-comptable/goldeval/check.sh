#!/usr/bin/env bash
# Verdict LOGIQUE (nom-agnostique) : existe-t-il un callable qui arrondit demi-supérieur
# ET un qui calcule le TTC ? Indépendant des noms (verdict API séparé). Discrimine round() natif.
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

def approx(a, b): return abs(float(a) - b) < 0.005  # < 0.01 : l'écart bancaire/half-up est discriminant

fs = funcs()

def is_round(fn):  # demi-supérieur (2 args)
    try:
        return approx(fn(2.675, 2), 2.68) and approx(fn(0.125, 2), 0.13) and approx(fn(2.674, 2), 2.67)
    except Exception:
        return False

def is_ttc(fn):  # TVA 20 % (1 arg)
    try:
        return approx(fn(10.0), 12.0)
    except Exception:
        return False

ok = any(is_round(f) for f in fs) and any(is_ttc(f) for f in fs)
print("logic OK" if ok else "logic FAIL : arrondi demi-supérieur et/ou TTC manquant (round() natif ?)")
sys.exit(0 if ok else 1)
PY
