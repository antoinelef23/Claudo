"""Tests BHV-5 / INV-4 : plafonnement des remises, goods_final jamais négatif."""

from pricing.model import Coupon
from pricing.coupons import resolve_coupons


def test_bhv5_fixed_capped_at_remaining_goods():
    """BHV-5 : FIXED value > goods → plafonné à goods, goods_final = 0."""
    c = Coupon(
        code="BIG",
        type="FIXED",
        value=99999,
        stackable=True,
        priority=5,
        valid_from=0,
        valid_to=100,
    )
    result = resolve_coupons(500, [c], current_day=10)
    assert result.coupon_discounts == 500  # plafonné à 500, pas 99999
    assert result.applied_codes == ["BIG"]


def test_bhv5_fixed_exact_match():
    """FIXED == goods → remise exacte, goods_final = 0."""
    c = Coupon(
        code="EXACT",
        type="FIXED",
        value=500,
        stackable=True,
        priority=1,
        valid_from=0,
        valid_to=100,
    )
    result = resolve_coupons(500, [c], current_day=10)
    assert result.coupon_discounts == 500


def test_bhv5_fixed_partial():
    """FIXED < goods → remise exacte, goods_final > 0."""
    c = Coupon(
        code="PARTIAL",
        type="FIXED",
        value=200,
        stackable=True,
        priority=1,
        valid_from=0,
        valid_to=100,
    )
    result = resolve_coupons(500, [c], current_day=10)
    assert result.coupon_discounts == 200


def test_inv4_cumulative_capped_at_initial_goods():
    """INV-4 : coupon_discounts cumulés ≤ goods_after_lines (deux coupons stackables)."""
    c1 = Coupon(
        code="A",
        type="FIXED",
        value=400,
        stackable=True,
        priority=1,
        valid_from=0,
        valid_to=100,
    )
    c2 = Coupon(
        code="B",
        type="FIXED",
        value=400,
        stackable=True,
        priority=2,
        valid_from=0,
        valid_to=100,
    )
    result = resolve_coupons(500, [c1, c2], current_day=10)
    # c1 prend 400, c2 ne peut prendre que 100 (reste)
    assert result.coupon_discounts == 500
    assert result.coupon_discounts <= 500  # INV-4


def test_percent_does_not_go_below_zero():
    """PERCENT à 100 % : plafonné à goods courants, jamais négatif."""
    c = Coupon(
        code="ALL",
        type="PERCENT",
        value=10000,
        stackable=True,
        priority=1,
        valid_from=0,
        valid_to=100,
    )
    result = resolve_coupons(300, [c], current_day=10)
    assert result.coupon_discounts == 300
    # goods restant = 0, pas négatif
