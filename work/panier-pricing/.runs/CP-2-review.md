# Revue CP-2 — panel de 1 — verdict agrégé : PASS (PASS)

## Paneliste 1 — claude-opus-4-8 — angle : revue complète
VERDICT: PASS

Tout est vert et conforme. Voici le rapport de revue.

---

# Rapport de revue — CP-2 (vertical slice : composition + réconciliation)

**Feature :** `panier-pricing` · **Tâche couverte :** T5 (`pricing.py` + EVAL-2 + EVAL-3) · **Angle :** revue complète
**Contexte :** CP-2 déjà rejeté une fois (12:34) → spec amendée v1.1.0 (BHV-6c, commit `5b0ab2d`), T3 `coupons.py` repris (`54999db`). Cette revue porte sur le slice complet `src/pricing/` tel qu'il intègre l'amendement.

## ✅ Conforme

- **Évals merge-gate vertes.** `pytest -m eval tests/pricing_pipeline` → **7 passed** (EVAL-2 property 1000 paniers seed=42 ; EVAL-3 a/b/c déterminisme & idempotence). Suite complète pricing → **86 passed**. `ruff check` → clean.
- **Régression du rejet corrigée et démontrée.** EX-9 (FREE_SHIPPING + coupon exclusif, BHV-6c) rejoue à l'identique : `coupon_discounts=2000, shipping=0, applied_coupons=['LIVRAISON','EXCL20']` — **MATCH**. EX-6 (FIXED plafonné, total>0) — **MATCH**. Le franco n'est plus évincé par l'exclusif.
- **BHV-6c implémenté proprement** — `coupons.py:44-45` sépare `free_shipping_coupons` des `discount_coupons` ; le comparatif exclusif (`coupons.py:58-64`) ne valorise jamais un FREE_SHIPPING (`_estimate` n'opère que sur PERCENT/FIXED). Aligné design §1 v1.1.0.
- **Ordre canonique (INV-5/BHV-6)** — `applied_codes` trié `(priority, code)` (`coupons.py:67-70`), appliqué dans cet ordre → `applied_coupons` déterministe. EVAL-3b (toutes permutations) vert.
- **Réconciliation INV-3 par construction** — `pricing.py:45-57` : `goods_final = goods_after_lines − coupon_discounts` (≥0 garanti par plafonnage ADR-4), `total = goods_final + shipping + tax`. EVAL-2 vérifie INV-1/2/3/4 sur 1000 paniers.
- **Ordre canonique figé ADR-2** — `pricing.py:33-54` : (1) subtotal → (2) tiers → (3) coupons → (4) goods_final → (5) port/franco → (6) TVA. La composition réutilise `tiers.line_discount`, `coupons.resolve_coupons`, `tax.compute_tax` sans réimplémenter aucune règle.
- **BHV-7/7a** — seuil inclus (`>=`) et franco par coupon : `pricing.py:48`. BHV-1 panier vide → tout à zéro, aucun port (`pricing.py:20-30`), testé y compris avec coupons présents.
- **Traçabilité** — commit T5 `9add5d5` porte `[INV-3, INV-5, BHV-1, BHV-2, BHV-7, BHV-7a, BHV-11, EVAL-2, EVAL-3]`, exactement les IDs de tasks.md T5. Tag `[auto]`, aucune ligne manuelle revendiquée.
- **Scope discipliné** — T5 ne touche que `src/pricing/pricing.py` + `tests/pricing_pipeline/` ; le redo T3 que `coupons.py` + ses tests. Aucun scope creep. Seuls fichiers non commités : `.runs/journal.jsonl` et `state.json` (artefacts de run, attendus).

## ⚠️ À noter (non bloquant)

- **EX-9 / BHV-6c pas encore dans une eval permanente.** Le cas du rejet est vérifié ici en démo manuelle et indirectement par EVAL-2, mais sa garde de non-régression dédiée (comparaison exacte de toutes les clés) est portée par **EVAL-1 (T6)**, hors périmètre CP-2. C'est conforme au plan — à confirmer vert au CP-3. Aucune action requise maintenant.
- **Dédoublonnage par `code`** (`coupons.py:31-37`) garde la première occurrence en ordre canonique si deux coupons partagent un `code` avec des attributs divergents. La spec (INV-6/BHV-9) ne contraint que « une seule occurrence » — choix déterministe acceptable, juste à garder en tête.

## ❌ Bloquants

Aucun.

---

Zéro écart : code conforme spec v1.1.0 + design v1.1.0, évals gate vertes, régression du précédent rejet corrigée et prouvée, traçabilité et scope propres. Le checkpoint reste `mode: blocking` → validation humaine de l'Owner requise pour la reprise (T6/T7/T8), ce verdict n'auto-valide pas.

VERDICT: PASS