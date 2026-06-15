"""Résolution des coupons : validité, dédoublonnage, cumul, plafond.

Implémente BHV-4, BHV-5, BHV-6, BHV-6a, BHV-6b, BHV-8, BHV-9, INV-4, INV-6.
Pur — ne dépend que de pricing.model.
"""

from __future__ import annotations

from dataclasses import dataclass

from pricing.model import Coupon


@dataclass(frozen=True)
class CouponOutcome:
    coupon_discounts: int
    applied_codes: list[str]
    free_shipping: bool


def resolve_coupons(
    goods_after_lines: int,
    coupons: list[Coupon],
    current_day: int,
) -> CouponOutcome:
    # (1) Filtrer la fenêtre de validité (BHV-8) — bornes incluses
    valid = [c for c in coupons if c.valid_from <= current_day <= c.valid_to]

    # (2) Dédoublonner par code (INV-6, BHV-9) — tri canonique d'abord pour déterminisme
    valid_sorted = sorted(valid, key=lambda c: (c.priority, c.code))
    seen: set[str] = set()
    deduped: list[Coupon] = []
    for c in valid_sorted:
        if c.code not in seen:
            seen.add(c.code)
            deduped.append(c)

    if not deduped:
        return CouponOutcome(coupon_discounts=0, applied_codes=[], free_shipping=False)

    # (3) Règle de cumul déterministe (BHV-6a / BHV-6b)
    has_exclusive = any(not c.stackable for c in deduped)

    if not has_exclusive:
        # BHV-6a : tous stackable → appliquer tous dans l'ordre canonique (déjà trié)
        to_apply = deduped
    else:
        # BHV-6b : au moins un exclusif → un seul coupon, le plus avantageux
        def _estimate(c: Coupon) -> int:
            if c.type == "PERCENT":
                return goods_after_lines * c.value // 10000
            if c.type == "FIXED":
                return min(c.value, goods_after_lines)
            return 0  # FREE_SHIPPING : remise monétaire nulle

        # Tri : remise desc (-), priority asc, code asc
        best = min(deduped, key=lambda c: (-_estimate(c), c.priority, c.code))
        to_apply = [best]

    # (4) Appliquer les coupons sélectionnés, plafonner à chaque étape (ADR-4)
    coupon_discounts = 0
    applied_codes: list[str] = []
    free_shipping = False
    current_goods = goods_after_lines

    for c in to_apply:
        if c.type == "FREE_SHIPPING":
            free_shipping = True
            applied_codes.append(c.code)
        elif c.type == "PERCENT":
            discount = min(current_goods * c.value // 10000, current_goods)
            coupon_discounts += discount
            current_goods -= discount
            applied_codes.append(c.code)
        elif c.type == "FIXED":
            discount = min(c.value, current_goods)
            coupon_discounts += discount
            current_goods -= discount
            applied_codes.append(c.code)

    return CouponOutcome(
        coupon_discounts=coupon_discounts,
        applied_codes=applied_codes,
        free_shipping=free_shipping,
    )
