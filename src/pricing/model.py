from __future__ import annotations

from dataclasses import dataclass

# Barème §4 spec : (qty_min, discount_bps), testé du plus haut palier au plus bas (INV-5)
TIER_SCHEDULE = ((50, 1000), (20, 500))

# Types de coupon valides (contrat §3 spec)
COUPON_TYPES = ("PERCENT", "FIXED", "FREE_SHIPPING")


@dataclass(frozen=True)
class Line:
    sku: str
    qty: int
    unit_price_cents: int


@dataclass(frozen=True)
class Coupon:
    code: str
    type: str
    value: int
    stackable: bool
    priority: int
    valid_from: int
    valid_to: int


@dataclass(frozen=True)
class Context:
    shipping_cents: int
    free_shipping_threshold_cents: int
    tax_bps: int
    current_day: int


def parse_cart(cart: dict) -> list[Line]:
    lines = []
    for raw in cart.get("lines", []):
        qty: int = raw["qty"]
        price: int = raw["unit_price_cents"]
        if qty < 0:
            raise ValueError(f"qty must be >= 0, got {qty!r}")
        if price < 0:
            raise ValueError(f"unit_price_cents must be >= 0, got {price!r}")
        lines.append(Line(sku=raw["sku"], qty=qty, unit_price_cents=price))
    return lines


def parse_coupons(raw: list[dict]) -> list[Coupon]:
    coupons = []
    for r in raw:
        t: str = r["type"]
        if t not in COUPON_TYPES:
            raise ValueError(
                f"Unknown coupon type: {t!r}. Must be one of {COUPON_TYPES}"
            )
        coupons.append(
            Coupon(
                code=r["code"],
                type=t,
                value=r["value"],
                stackable=r["stackable"],
                priority=r["priority"],
                valid_from=r["valid_from"],
                valid_to=r["valid_to"],
            )
        )
    return coupons


def parse_context(ctx: dict) -> Context:
    return Context(
        shipping_cents=ctx["shipping_cents"],
        free_shipping_threshold_cents=ctx["free_shipping_threshold_cents"],
        tax_bps=ctx["tax_bps"],
        current_day=ctx["current_day"],
    )
