#!/usr/bin/env bash
# Eval-or CACHÉE : pièges sur les bornes de paliers et le clamp.
# Robuste au nom de fichier : on cherche compute_total dans N'IMPORTE quel module du
# répertoire (le contrat-fichier n'est pas l'objet du test ; les paliers le sont).
set -uo pipefail
python3 - <<'PY'
import sys, importlib.util, pathlib
sys.path.insert(0, ".")

def load_fn(name):
    for p in pathlib.Path(".").rglob("*.py"):
        if "goldeval" in p.parts:
            continue
        try:
            spec = importlib.util.spec_from_file_location(p.stem, p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception:
            continue
        if hasattr(mod, name):
            return getattr(mod, name)
    return None

compute_total = load_fn("compute_total")
if compute_total is None:
    print("fonction compute_total introuvable dans le répertoire"); sys.exit(1)

def a(x, y): return abs(float(x) - y) < 0.01

# On teste les PALIERS et le CLAMP (la logique), pas la clé is_estimate (orthogonale).
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
print("golden remise-paliers OK"); sys.exit(0)
PY
