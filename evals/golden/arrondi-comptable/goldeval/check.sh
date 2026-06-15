#!/usr/bin/env bash
# Eval-or CACHÉE : piège l'arrondi bancaire de round() vs le demi-supérieur comptable.
set -uo pipefail
python3 - <<'PY'
import sys
sys.path.insert(0, ".")
try:
    from compute import round_half_up, compute_ttc
except Exception as e:
    print(f"import impossible: {e}"); sys.exit(1)

# tolérance 0.005 : la différence bancaire/demi-supérieur est de 0.01, donc discriminante
def ok(got, want): return abs(float(got) - want) < 0.005

cases_r = [((2.675, 2), 2.68), ((0.125, 2), 0.13), ((1.005, 2), 1.01), ((2.674, 2), 2.67)]
for args, want in cases_r:
    got = round_half_up(*args)
    if not ok(got, want):
        print(f"round_half_up{args} = {got} attendu {want} (arrondi bancaire ?)"); sys.exit(1)

if not ok(compute_ttc(10.0), 12.00):
    print(f"compute_ttc(10.0) = {compute_ttc(10.0)} attendu 12.00"); sys.exit(1)
print("golden arrondi-comptable OK"); sys.exit(0)
PY
