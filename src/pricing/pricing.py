"""Orchestrateur de calcul : compose tiers + coupons + tax dans l'ordre canonique (ADR-2).

Implémente INV-3, INV-5, BHV-1, BHV-2, BHV-7, BHV-7a, BHV-11.
"""

from __future__ import annotations

from pricing.coupons import resolve_coupons
from pricing.model import parse_cart, parse_context, parse_coupons
from pricing.tax import compute_tax
from pricing.tiers import line_discount


def price(cart: dict, coupons: list[dict], context: dict) -> dict:
    lines = parse_cart(cart)
    coupon_list = parse_coupons(coupons)
    ctx = parse_context(context)

    # BHV-1 — panier vide : tout à zéro, aucun port, aucun coupon appliqué
    if not lines:
        return {
            "goods_subtotal": 0,
            "line_discounts": 0,
            "coupon_discounts": 0,
            "goods_final": 0,
            "shipping": 0,
            "tax": 0,
            "total": 0,
            "applied_coupons": [],
        }

    # (1) goods_subtotal — somme qty * unit_price_cents
    goods_subtotal = sum(line.qty * line.unit_price_cents for line in lines)

    # (2) line_discounts — remises palier par ligne, floor (ADR-1)
    total_line_discounts = sum(line_discount(line) for line in lines)

    # base transmise aux coupons : marchandise après remises de ligne
    goods_after_lines = goods_subtotal - total_line_discounts

    # (3) coupon_discounts — tri canonique interne, plafond, cumul (ADR-4)
    outcome = resolve_coupons(goods_after_lines, coupon_list, ctx.current_day)

    # (4) goods_final ≥ 0 garanti par le plafonnage dans resolve_coupons (ADR-4)
    goods_final = goods_after_lines - outcome.coupon_discounts

    # (5) port / franco (BHV-7, BHV-7a — seuil INCLUS)
    if goods_final >= ctx.free_shipping_threshold_cents or outcome.free_shipping:
        shipping = 0
    else:
        shipping = ctx.shipping_cents

    # (6) TVA half-up une seule fois sur la base taxable totale (ADR-3, INV-7)
    tax = compute_tax(goods_final + shipping, ctx.tax_bps)

    # BHV-11 / INV-3 : réconciliation garantie par construction
    total = goods_final + shipping + tax

    return {
        "goods_subtotal": goods_subtotal,
        "line_discounts": total_line_discounts,
        "coupon_discounts": outcome.coupon_discounts,
        "goods_final": goods_final,
        "shipping": shipping,
        "tax": tax,
        "total": total,
        "applied_coupons": outcome.applied_codes,
    }
