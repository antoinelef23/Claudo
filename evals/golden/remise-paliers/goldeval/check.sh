#!/usr/bin/env bash
# Eval-or CACHÉE : pièges sur les bornes de paliers et le clamp.
set -uo pipefail
python3 - <<'PY'
import sys
sys.path.insert(0, ".")
try:
    from compute import compute_total
except Exception as e:
    print(f"import impossible: {e}"); sys.exit(1)

def a(x, y): return abs(float(x) - y) < 0.01

cases = [
    ((1000, 0),    "products_eur", 1000.00),   # borne basse : 0 %
    ((1000.01, 0), "products_eur", 950.01),     # juste au-dessus : 5 %
    ((5000, 10),   "products_eur", 4750.00),    # borne haute du 5 % (inclusive)
    ((5000, 10),   "installation_eur", 450.00),
    ((5000.01, 0), "products_eur", 4500.01),    # juste au-dessus : 10 %
    ((-100, -5),   "total_eur", 0.00),          # clamp INV-1
]
for args, key, want in cases:
    got = compute_total(*args)
    if not a(got[key], want):
        print(f"{args} {key}={got.get(key)} attendu {want}"); sys.exit(1)
    if got.get("is_estimate") is not True:
        print(f"{args}: is_estimate != True"); sys.exit(1)
print("golden remise-paliers OK"); sys.exit(0)
PY
