# Revue CP-1 — panel de 1 — verdict agrégé : PASS (PASS)

## Paneliste 1 — claude-opus-4-8 — angle : revue complète
VERDICT: PASS

Tout est en main. Voici le dossier de revue.

---

## Rapport de revue — CP-1 · Fondation `model.py` (T1)

**Angle : revue complète.** Tâches couvertes : T1 `[INV-1, INV-2]`. Checkpoint `mode: auto`.

### ✅ Conforme

- **Traçabilité commit ↔ spec** — `2738f63` référence `[INV-1, INV-2]`, exactement les IDs déclarés dans T1 (`tasks.md:48`). Tag `[auto]` cohérent avec CP-1 auto.
- **Scope `files_touched`** — diff strictement limité à `src/pricing/__init__.py`, `src/pricing/model.py`, `tests/pricing_model/` (+ journal/tasks). Aucun fichier d'une autre tâche (tiers/coupons/tax/pricing/cli) touché. Zéro scope creep.
- **Signatures pinnées (design §5)** — conformité à l'identique :
  - `TIER_SCHEDULE = ((50, 1000), (20, 500))` — `model.py:6` ✓ (ordre haut→bas, design:123)
  - `COUPON_TYPES` — `model.py:9` ✓
  - `Line` / `Coupon` / `Context` `frozen=True`, champs exacts — `model.py:12,19,30` ✓
  - `parse_cart` / `parse_coupons` / `parse_context` — `model.py:38,51,73` ✓
- **ADR-1 (tout entier, aucun float)** — aucun flottant introduit ; `model.py` ne contient aucune arithmétique de prix.
- **Garde INV-2 en amont** — `parse_cart` rejette `qty < 0` (`model.py:43-44`) et `unit_price_cents < 0` (`model.py:45-46`) ; `parse_coupons` rejette un `type` hors `COUPON_TYPES` (`model.py:55-58`). Tests dédiés `test_model.py:74-83,147-160`.
- **Aucune logique de calcul** — exigence T1 « AUCUNE logique de prix » vérifiée mécaniquement par `test_model_has_no_pricing_logic` (`test_model.py:190-196`) : pas de `price`/`compute_tax`/`line_discount`/`resolve_coupons`. ✓
- **Qualité** — `uv run pytest -q tests/pricing_model` → **17 passed**. `ruff check` → *All checks passed*. `ruff format --check` → *2 files already formatted*. Import `pricing.model` OK (`pythonpath=["src"]`, `pyproject.toml`). Aucun secret, aucun TODO orphelin.
- **`done_when` / `verify`** — satisfaits (tests bornes + dataclasses gelées verts).

### ⚠️ Écarts à arbitrer (mineur, non bloquant)

- **Validation de type non stricte** — les parseurs vérifient le signe (`< 0`) mais pas que `qty` / `unit_price_cents` / `value` sont des `int` : un `qty=1.5` traverserait `parse_cart` sans rejet. INV-1 (« aucun float ne sort de `price` ») est défendu en aval, et **le prompt T1 ne demandait que** le rejet négatif + type de coupon inconnu — donc strictement dans le périmètre. Note pour info à l'Owner : si l'on veut blinder INV-1 dès l'entrée, ce serait une garde `isinstance(..., int)` à ajouter (sans amender la spec). Hors scope T1.

### ❌ Bloquants

Aucun.

---

Fondation conforme au contrat, tests verts, ruff propre, signatures design §5 respectées à l'identique, scope et traçabilité corrects. L'unique observation est mineure et hors périmètre de T1.

VERDICT: PASS