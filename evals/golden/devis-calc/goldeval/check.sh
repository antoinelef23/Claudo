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
    # Exemples de la spec (§5)
    ((1500, 10), {"products_eur": 1500.0, "installation_eur": 450.0, "total_eur": 1950.0}),
    ((2500, 20), {"products_eur": 2375.0, "installation_eur": 900.0, "total_eur": 3275.0}),
    ((100, 0), {"total_eur": 100.0}),
    # Held-out (finding M8) : valeurs HORS spec, dérivées de la formule (remise BHV-2 si
    # produits > 2000 ; pose 45 €/m² ; clamp INV-1) — défont une table de correspondance.
    ((1000.50, 5), {"total_eur": 1225.50}),  # sous le seuil
    ((3000, 15), {"total_eur": 3525.0}),  # 2× le seuil → remise
    ((2000.00, 25), {"total_eur": 3125.0}),  # seuil exact (BHV-2a strict) → PAS de remise
    ((2000.01, 25), {"total_eur": 3025.01}),  # juste au-dessus → remise
    ((10000, 100), {"total_eur": 14000.0}),
    ((0.01, 0.01), {"total_eur": 0.46}),  # minimal non nul
    ((-5, 10), {"total_eur": 450.0}),  # produits clampés (INV-1)
    ((5000, -10), {"total_eur": 4750.0}),  # surface clampée (INV-1)
]

def works(fn):
    try:
        for args, exp in cases:
            r = fn(*args)
            for k, v in exp.items():
                if not approx(r[k], v):
                    return False
        # clamp INV-1 ET is_estimate MUST valoir True (INV-2 — finding M9)
        return float(fn(-100, -5)["total_eur"]) >= 0 and fn(1500, 10).get("is_estimate") is True
    except Exception:
        return False

ok = any(works(f) for f in funcs())
print("logic OK" if ok else "logic FAIL : aucun callable ne calcule correctement")
sys.exit(0 if ok else 1)
PY
