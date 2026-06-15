"""Tests INV-5 : indifférence à l'ordre d'entrée du tableau coupons."""

from pricing.model import Coupon
from pricing.coupons import resolve_coupons


def _make_coupons():
    return [
        Coupon(
            code="BETA",
            type="PERCENT",
            value=1000,
            stackable=True,
            priority=10,
            valid_from=0,
            valid_to=100,
        ),
        Coupon(
            code="ALPHA",
            type="FIXED",
            value=50,
            stackable=True,
            priority=5,
            valid_from=0,
            valid_to=100,
        ),
        Coupon(
            code="GAMMA",
            type="PERCENT",
            value=500,
            stackable=True,
            priority=7,
            valid_from=0,
            valid_to=100,
        ),
    ]


def test_order_indifference_all_stackable():
    """INV-5 : permuter les coupons stackables → même CouponOutcome."""
    coupons = _make_coupons()
    r1 = resolve_coupons(2000, coupons, current_day=10)
    r2 = resolve_coupons(2000, list(reversed(coupons)), current_day=10)
    r3 = resolve_coupons(2000, [coupons[2], coupons[0], coupons[1]], current_day=10)
    assert r1 == r2 == r3


def test_order_indifference_exclusive_present():
    """INV-5 : présence d'un exclusif — l'ordre d'entrée ne change pas le gagnant."""
    c_excl = Coupon(
        code="EXCL20",
        type="PERCENT",
        value=2000,
        stackable=False,
        priority=20,
        valid_from=0,
        valid_to=100,
    )
    c_stk = Coupon(
        code="STACK5",
        type="PERCENT",
        value=500,
        stackable=True,
        priority=10,
        valid_from=0,
        valid_to=100,
    )
    r1 = resolve_coupons(10000, [c_excl, c_stk], current_day=10)
    r2 = resolve_coupons(10000, [c_stk, c_excl], current_day=10)
    assert r1 == r2
    assert r1.applied_codes == ["EXCL20"]


def test_order_indifference_with_expired():
    """INV-5 : coupon expiré présent — l'ordre ne change pas le résultat."""
    valid = Coupon(
        code="VALID",
        type="PERCENT",
        value=1000,
        stackable=True,
        priority=1,
        valid_from=0,
        valid_to=100,
    )
    expired = Coupon(
        code="OLD",
        type="PERCENT",
        value=5000,
        stackable=True,
        priority=1,
        valid_from=0,
        valid_to=5,
    )
    r1 = resolve_coupons(1000, [valid, expired], current_day=10)
    r2 = resolve_coupons(1000, [expired, valid], current_day=10)
    assert r1 == r2
    assert r1.applied_codes == ["VALID"]
