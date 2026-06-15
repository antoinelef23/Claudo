#!/usr/bin/env bash
# Eval-or CACHÉE : jugement objectif du scorecard. Le modèle ne la voit jamais.
# Sortie 0 = le compute.py produit par le modèle est conforme à la spec.
set -uo pipefail
python3 - <<'PY'
import sys
sys.path.insert(0, ".")
try:
    from compute import compute_quote
except Exception as e:
    print(f"import impossible: {e}"); sys.exit(1)

def approx(a, b): return abs(a - b) < 0.01

cases = [
    ((1500, 10), {"products_eur": 1500.00, "installation_eur": 450.00, "total_eur": 1950.00}),
    ((2500, 20), {"products_eur": 2375.00, "installation_eur": 900.00, "total_eur": 3275.00}),
    ((100, 0),   {"total_eur": 100.00}),
]
for (args, expected) in cases:
    got = compute_quote(*args)
    for k, v in expected.items():
        if not approx(float(got[k]), v):
            print(f"EX {args}: {k}={got.get(k)} attendu {v}"); sys.exit(1)
    if got.get("is_estimate") is not True:
        print(f"EX {args}: is_estimate != True"); sys.exit(1)

# INV-1 : entrées négatives → total >= 0
if compute_quote(-100, -5)["total_eur"] < 0:
    print("INV-1 violé sur entrées négatives"); sys.exit(1)
print("golden OK"); sys.exit(0)
PY
