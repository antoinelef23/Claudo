"""Tests BHV-9 / INV-6 : dédoublonnage par code."""

from pricing.model import Coupon
from pricing.coupons import resolve_coupons


def test_bhv9_duplicate_code_counted_once():
    """Deux entrées de même code = une seule occurrence (INV-6)."""
    c1 = Coupon(
        code="DUP",
        type="PERCENT",
        value=1000,
        stackable=True,
        priority=1,
        valid_from=0,
        valid_to=100,
    )
    c2 = Coupon(
        code="DUP",
        type="PERCENT",
        value=1000,
        stackable=True,
        priority=1,
        valid_from=0,
        valid_to=100,
    )
    result = resolve_coupons(1000, [c1, c2], current_day=10)
    assert result.applied_codes.count("DUP") == 1
    assert result.coupon_discounts == 100  # 10 % une seule fois


def test_inv6_applied_codes_no_duplicate():
    """applied_codes ne liste un code qu'une fois, même avec 3 doublons."""
    c = Coupon(
        code="X",
        type="FIXED",
        value=50,
        stackable=True,
        priority=1,
        valid_from=0,
        valid_to=100,
    )
    result = resolve_coupons(500, [c, c, c], current_day=5)
    assert result.applied_codes == ["X"]
    assert result.coupon_discounts == 50


def test_bhv9_different_codes_both_applied():
    """Deux codes distincts stackable → tous deux appliqués (pas de fausse dédup)."""
    c1 = Coupon(
        code="A",
        type="PERCENT",
        value=500,
        stackable=True,
        priority=1,
        valid_from=0,
        valid_to=100,
    )
    c2 = Coupon(
        code="B",
        type="PERCENT",
        value=500,
        stackable=True,
        priority=2,
        valid_from=0,
        valid_to=100,
    )
    result = resolve_coupons(2000, [c1, c2], current_day=10)
    assert set(result.applied_codes) == {"A", "B"}
    assert result.coupon_discounts > 0
