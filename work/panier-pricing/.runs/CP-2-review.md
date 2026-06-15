# Revue CP-2 — panel de 1 — verdict agrégé : WARN (WARN)

## Paneliste 1 — claude-opus-4-8 — angle : revue complète
VERDICT: WARN

Revue complète terminée. Tous les contrôles passent ; voici le dossier de revue.

---

# Rapport de revue — CP-2 (vertical slice : composition + réconciliation)

**Feature :** `panier-pricing` · **Tâche couverte :** T5 (`pricing.py` + EVAL-2 + EVAL-3) · **Angle :** revue complète · **Mode checkpoint :** blocking

## ✅ Conforme

- **Traçabilité exacte** — commit `9add5d5` référence `[INV-3, INV-5, BHV-1, BHV-2, BHV-7, BHV-7a, BHV-11, EVAL-2, EVAL-3]`, strictement identique au `implements:` de T5 (`tasks.md:161`). Marqué `[auto]` (généré), aucune ligne manuscrite à justifier.
- **Scope propre** — le diff ne touche que les `files_touched` de T5 (`src/pricing/pricing.py`, `tests/pricing_pipeline/`) + fichiers de suivi (`.runs/`, run log). Aucun scope creep, aucune modification de `model/tiers/coupons/tax`.
- **Composition, pas de réimplémentation (ADR-2)** — `pricing.py:8-11` réutilise `tiers.line_discount`, `coupons.resolve_coupons`, `tax.compute_tax`. Aucune règle métier dupliquée. Ordre canonique figé respecté (`pricing.py:33-57`).
- **INV-3 par construction** — `total = goods_final + shipping + tax` (`pricing.py:57`) ; vérifié par EVAL-2 sur 1000 paniers et les tests `TestReconciliation`.
- **INV-2 / INV-4 / ADR-4** — `goods_final` jamais < 0 (plafonnage dans `coupons.py:71-78`) ; `coupon_discounts ≤ goods_after_lines` ⇒ `line_discounts + coupon_discounts ≤ goods_subtotal`. Confirmé par EVAL-2 (INV-4).
- **BHV-1 / BHV-7 / BHV-7a** — panier vide → tout à zéro, **aucun port** (`pricing.py:20-30`) ; franco seuil **inclus** (`>=`, `pricing.py:48`) ; `FREE_SHIPPING` valide annule le port. Couverts par `test_pricing_behaviors.py`.
- **INV-5 (déterminisme/ordre)** — tri canonique interne aux coupons ; EVAL-3b teste **toutes** les permutations, EVAL-3c l'idempotence des doublons. Aucun `now()`/aléa hors seed fixe.
- **Qualité** — `ruff check` propre (src + tests), tous montants `int` (INV-1 vérifié par EVAL-2 + `test_all_values_are_int`), pas de secret ni TODO.
- **Evals & tests verts** — `pytest -m eval tests/pricing_pipeline` : 7 passed ; `pytest tests/pricing_pipeline` : 19 passed ; suite eval repo complète : **1078 passed** ; suite pricing complète : **84 passed**.
- **Démo BHV-6b / EX-6 (lecture code)** — exclusif sélectionné par `min(key=(-estimate, priority, code))` (`coupons.py:49-57`) : EXCL20 (2000) bat STACK5 (500), FIXED plafonné laisse `goods_final=0` avec `total>0`. Logique conforme à EX-7/EX-6 (vérification exhaustive viendra avec EVAL-1/T6).

## ⚠️ À arbitrer par l'Owner (1)

- **Interaction `FREE_SHIPPING` × mode exclusif — sous-spécifiée.** En présence d'un coupon exclusif (`coupons.py:48-57`), la sélection « meilleure remise unique » (BHV-6b) attribue à `FREE_SHIPPING` une remise monétaire de `0` (`coupons.py:54`). Conséquence : un `FREE_SHIPPING` cumulable est **écarté** dès qu'un coupon exclusif à remise > 0 est présent (le port redevient dû), et en cas d'égalité à 0 le départage `(priority, code)` peut préférer un coupon dégénéré (ex. `FIXED value=0`) au `FREE_SHIPPING`. C'est une **lecture défendable** de BHV-6b (« plus grosse remise », et la remise monétaire d'un `FREE_SHIPPING` est nulle par contrat §3), et **aucun invariant n'est violé** — mais la spec ne tranche pas explicitement la valorisation du franco dans le comparatif exclusif. À confirmer côté métier ; si la règle doit changer, c'est un **amendement spec** (commit séparé), pas un patch code.

## ❌ Bloquant

- Aucun.

---

Aucun écart sur les invariants, la traçabilité, le scope ou la qualité ; un seul point de spec sous-spécifié à confirmer par le métier (CP-2 est blocking, donc l'arbitrage humain est de toute façon requis).

VERDICT: WARN