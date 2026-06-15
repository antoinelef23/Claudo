"""Tests BHV-8 : validité de la fenêtre temporelle des coupons."""

from pricing.model import Coupon
from pricing.coupons import resolve_coupons


def _coupon(**kwargs) -> Coupon:
    defaults = dict(
        code="C",
        type="PERCENT",
        value=1000,
        stackable=True,
        priority=1,
        valid_from=0,
        valid_to=100,
    )
    defaults.update(kwargs)
    return Coupon(**defaults)


def test_bhv8_coupon_expired_ignored():
    """current_day > valid_to → ignoré, pas dans applied_codes."""
    c = _coupon(code="OLD", valid_from=0, valid_to=5)
    result = resolve_coupons(1000, [c], current_day=10)
    assert result.coupon_discounts == 0
    assert result.applied_codes == []
    assert result.free_shipping is False


def test_bhv8_coupon_not_yet_valid_ignored():
    """current_day < valid_from → ignoré."""
    c = _coupon(code="FUTURE", valid_from=20, valid_to=100)
    result = resolve_coupons(1000, [c], current_day=10)
    assert result.coupon_discounts == 0
    assert result.applied_codes == []


def test_bhv8_valid_on_lower_boundary():
    """current_day == valid_from → INCLUS, appliqué (BHV-8)."""
    c = _coupon(code="C", value=1000, valid_from=10, valid_to=100)
    result = resolve_coupons(1000, [c], current_day=10)
    assert result.coupon_discounts == 100  # floor(1000 * 1000 / 10000)
    assert result.applied_codes == ["C"]


def test_bhv8_valid_on_upper_boundary():
    """current_day == valid_to → INCLUS, appliqué (BHV-8)."""
    c = _coupon(code="C", value=1000, valid_from=0, valid_to=10)
    result = resolve_coupons(1000, [c], current_day=10)
    assert result.coupon_discounts == 100
    assert result.applied_codes == ["C"]


def test_bhv8_expired_among_valid_ignored():
    """Coupon expiré ignoré même si d'autres sont valides."""
    expired = _coupon(code="OLD", value=5000, valid_from=0, valid_to=5)
    valid = _coupon(code="NEW", value=1000, valid_from=0, valid_to=100)
    result = resolve_coupons(1000, [expired, valid], current_day=10)
    assert result.applied_codes == ["NEW"]
    assert result.coupon_discounts == 100
