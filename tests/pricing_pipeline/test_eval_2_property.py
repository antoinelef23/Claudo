"""EVAL-2 — property-based : INV-1, INV-2, INV-3, INV-4 sur 1000 paniers aléatoires.

@pytest.mark.eval — merge gate.
Seed fixe pour déterminisme (INV-5).
"""

import random

import pytest

from pricing.pricing import price

_SEED = 42
_N_CARTS = 1000

_COUPON_TYPES = ("PERCENT", "FIXED", "FREE_SHIPPING")


def _gen_cart(rng: random.Random) -> dict:
    n_lines = rng.randint(0, 5)
    lines = [
        {
            "sku": f"SKU{rng.randint(1, 50)}",
            "qty": rng.randint(0, 60),
            "unit_price_cents": rng.randint(0, 10000),
        }
        for _ in range(n_lines)
    ]
    return {"lines": lines}


def _gen_coupons(rng: random.Random) -> list[dict]:
    n = rng.randint(0, 4)
    coupons = []
    for i in range(n):
        t = rng.choice(_COUPON_TYPES)
        coupons.append(
            {
                "code": f"C{i}_{rng.randint(0, 9)}",
                "type": t,
                "value": rng.randint(0, 3000) if t != "FREE_SHIPPING" else 0,
                "stackable": rng.choice([True, False]),
                "priority": rng.randint(1, 20),
                "valid_from": rng.randint(0, 15),
                "valid_to": rng.randint(5, 20),
            }
        )
    return coupons


def _gen_context(rng: random.Random) -> dict:
    return {
        "shipping_cents": rng.randint(0, 1000),
        "free_shipping_threshold_cents": rng.randint(1000, 10000),
        "tax_bps": rng.randint(0, 2500),
        "current_day": rng.randint(0, 20),
    }


@pytest.mark.eval
def test_eval_2_properties_on_1000_random_carts():
    """EVAL-2 : INV-1/INV-2/INV-3/INV-4 sur 1000 paniers (seed fixe)."""
    rng = random.Random(_SEED)
    violations = []

    for i in range(_N_CARTS):
        cart = _gen_cart(rng)
        coupons = _gen_coupons(rng)
        ctx = _gen_context(rng)

        result = price(cart, coupons, ctx)

        # INV-1 — tous les montants sont des int
        int_keys = [k for k in result if k != "applied_coupons"]
        for key in int_keys:
            if not isinstance(result[key], int):
                violations.append(
                    f"[cart {i}] INV-1: {key} is {type(result[key])!r}, not int"
                )

        # INV-2 — jamais négatif
        if result["total"] < 0:
            violations.append(f"[cart {i}] INV-2: total={result['total']} < 0")
        if result["goods_final"] < 0:
            violations.append(
                f"[cart {i}] INV-2: goods_final={result['goods_final']} < 0"
            )

        # INV-3 — réconciliation exacte
        expected_total = result["goods_final"] + result["shipping"] + result["tax"]
        if result["total"] != expected_total:
            violations.append(
                f"[cart {i}] INV-3: total={result['total']} != "
                f"goods_final+shipping+tax={expected_total}"
            )

        # INV-4 — remise totale ≤ goods_subtotal
        total_discount = result["line_discounts"] + result["coupon_discounts"]
        if total_discount > result["goods_subtotal"]:
            violations.append(
                f"[cart {i}] INV-4: line_discounts+coupon_discounts={total_discount} "
                f"> goods_subtotal={result['goods_subtotal']}"
            )

    assert not violations, f"{len(violations)} violation(s):\n" + "\n".join(
        violations[:20]
    )
