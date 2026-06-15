import dataclasses
import pytest

from pricing.model import (
    COUPON_TYPES,
    TIER_SCHEDULE,
    Context,
    Coupon,
    Line,
    parse_cart,
    parse_context,
    parse_coupons,
)


# --- Constants ---


def test_tier_schedule_highest_first():
    assert TIER_SCHEDULE == ((50, 1000), (20, 500))


def test_coupon_types():
    assert COUPON_TYPES == ("PERCENT", "FIXED", "FREE_SHIPPING")


# --- Dataclasses: frozen (INV-1) ---


def test_line_frozen():
    line = Line(sku="A", qty=1, unit_price_cents=100)
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        line.qty = 2  # type: ignore[misc]


def test_coupon_frozen():
    c = Coupon(
        code="X",
        type="PERCENT",
        value=500,
        stackable=True,
        priority=1,
        valid_from=0,
        valid_to=100,
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        c.value = 999  # type: ignore[misc]


def test_context_frozen():
    ctx = Context(
        shipping_cents=500,
        free_shipping_threshold_cents=5000,
        tax_bps=2000,
        current_day=10,
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        ctx.tax_bps = 0  # type: ignore[misc]


# --- parse_cart ---


def test_parse_cart_valid():
    cart = {"lines": [{"sku": "A", "qty": 2, "unit_price_cents": 1000}]}
    lines = parse_cart(cart)
    assert lines == [Line(sku="A", qty=2, unit_price_cents=1000)]


def test_parse_cart_empty():
    assert parse_cart({"lines": []}) == []


def test_parse_cart_rejects_negative_qty():
    # INV-2: garde anti-négatif en amont du calcul
    with pytest.raises(ValueError):
        parse_cart({"lines": [{"sku": "A", "qty": -1, "unit_price_cents": 100}]})


def test_parse_cart_rejects_negative_price():
    # INV-2: unit_price_cents < 0 interdit
    with pytest.raises(ValueError):
        parse_cart({"lines": [{"sku": "A", "qty": 1, "unit_price_cents": -1}]})


def test_parse_cart_zero_qty_ok():
    lines = parse_cart({"lines": [{"sku": "A", "qty": 0, "unit_price_cents": 0}]})
    assert lines[0].qty == 0


def test_parse_cart_multiple_lines():
    cart = {
        "lines": [
            {"sku": "A", "qty": 1, "unit_price_cents": 100},
            {"sku": "B", "qty": 3, "unit_price_cents": 200},
        ]
    }
    lines = parse_cart(cart)
    assert len(lines) == 2
    assert lines[1].sku == "B"


# --- parse_coupons ---


def test_parse_coupons_valid_percent():
    raw = [
        {
            "code": "W10",
            "type": "PERCENT",
            "value": 1000,
            "stackable": True,
            "priority": 1,
            "valid_from": 0,
            "valid_to": 100,
        }
    ]
    coupons = parse_coupons(raw)
    assert len(coupons) == 1
    assert coupons[0] == Coupon(
        code="W10",
        type="PERCENT",
        value=1000,
        stackable=True,
        priority=1,
        valid_from=0,
        valid_to=100,
    )


def test_parse_coupons_valid_all_types():
    for t in ("PERCENT", "FIXED", "FREE_SHIPPING"):
        raw = [
            {
                "code": "C",
                "type": t,
                "value": 0,
                "stackable": True,
                "priority": 1,
                "valid_from": 0,
                "valid_to": 100,
            }
        ]
        assert parse_coupons(raw)[0].type == t


def test_parse_coupons_rejects_unknown_type():
    raw = [
        {
            "code": "X",
            "type": "BOGUS",
            "value": 0,
            "stackable": True,
            "priority": 1,
            "valid_from": 0,
            "valid_to": 100,
        }
    ]
    with pytest.raises(ValueError):
        parse_coupons(raw)


def test_parse_coupons_empty():
    assert parse_coupons([]) == []


# --- parse_context ---


def test_parse_context_valid():
    ctx = parse_context(
        {
            "shipping_cents": 500,
            "free_shipping_threshold_cents": 5000,
            "tax_bps": 2000,
            "current_day": 10,
        }
    )
    assert ctx == Context(
        shipping_cents=500,
        free_shipping_threshold_cents=5000,
        tax_bps=2000,
        current_day=10,
    )


# --- No pricing logic in model ---


def test_model_has_no_pricing_logic():
    import pricing.model as m

    assert not hasattr(m, "price")
    assert not hasattr(m, "compute_tax")
    assert not hasattr(m, "line_discount")
    assert not hasattr(m, "resolve_coupons")
