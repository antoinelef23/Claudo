"""Tests BHV-4, BHV-6a, BHV-6b : règle de cumul (stackable vs exclusif)."""

from pricing.model import Coupon
from pricing.coupons import resolve_coupons


def test_bhv4_percent_stackable_applied():
    """BHV-4 : coupon PERCENT valide et cumulable → floor(goods * bps / 10000)."""
    c = Coupon(
        code="WELCOME10",
        type="PERCENT",
        value=1000,
        stackable=True,
        priority=10,
        valid_from=0,
        valid_to=100,
    )
    result = resolve_coupons(2000, [c], current_day=10)
    assert result.coupon_discounts == 200  # floor(2000 * 1000 / 10000)
    assert result.applied_codes == ["WELCOME10"]
    assert result.free_shipping is False


def test_bhv6a_all_stackable_applied_in_canonical_order():
    """BHV-6a : tous stackable → tous appliqués, ordre priority asc puis code alpha."""
    # c_beta priority=10, c_alpha priority=5 → ordre canonique : ALPHA puis BETA
    c_beta = Coupon(
        code="BETA",
        type="PERCENT",
        value=1000,
        stackable=True,
        priority=10,
        valid_from=0,
        valid_to=100,
    )
    c_alpha = Coupon(
        code="ALPHA",
        type="PERCENT",
        value=500,
        stackable=True,
        priority=5,
        valid_from=0,
        valid_to=100,
    )
    # goods=2000
    # ALPHA: floor(2000*500/10000)=100 → current=1900
    # BETA:  floor(1900*1000/10000)=190 → current=1710
    result = resolve_coupons(2000, [c_beta, c_alpha], current_day=10)
    assert result.applied_codes == ["ALPHA", "BETA"]
    assert result.coupon_discounts == 290


def test_bhv6a_same_priority_code_alpha_order():
    """BHV-6a tie-break : même priority → ordre alphabétique du code."""
    c_z = Coupon(
        code="ZZZ",
        type="PERCENT",
        value=500,
        stackable=True,
        priority=5,
        valid_from=0,
        valid_to=100,
    )
    c_a = Coupon(
        code="AAA",
        type="PERCENT",
        value=500,
        stackable=True,
        priority=5,
        valid_from=0,
        valid_to=100,
    )
    result = resolve_coupons(1000, [c_z, c_a], current_day=10)
    assert result.applied_codes == ["AAA", "ZZZ"]


def test_bhv6b_exclusive_present_only_best_applied():
    """BHV-6b : au moins un exclusif → un seul coupon, le plus avantageux."""
    c_stack = Coupon(
        code="STACK5",
        type="PERCENT",
        value=500,
        stackable=True,
        priority=10,
        valid_from=0,
        valid_to=100,
    )
    c_excl = Coupon(
        code="EXCL20",
        type="PERCENT",
        value=2000,
        stackable=False,
        priority=20,
        valid_from=0,
        valid_to=100,
    )
    # goods=10000 : STACK5→500, EXCL20→2000 ; EXCL20 gagne
    result = resolve_coupons(10000, [c_stack, c_excl], current_day=10)
    assert result.applied_codes == ["EXCL20"]
    assert result.coupon_discounts == 2000


def test_bhv6b_stackable_beats_exclusive_if_bigger():
    """BHV-6b : le stackable est retenu si sa remise est plus grosse que l'exclusif."""
    c_stack = Coupon(
        code="STACK50",
        type="PERCENT",
        value=5000,
        stackable=True,
        priority=1,
        valid_from=0,
        valid_to=100,
    )
    c_excl = Coupon(
        code="EXCL5",
        type="PERCENT",
        value=500,
        stackable=False,
        priority=2,
        valid_from=0,
        valid_to=100,
    )
    # goods=1000 : STACK50→500, EXCL5→50 ; STACK50 gagne
    result = resolve_coupons(1000, [c_stack, c_excl], current_day=10)
    assert result.applied_codes == ["STACK50"]
    assert result.coupon_discounts == 500


def test_bhv6b_tie_broken_by_priority_then_code():
    """BHV-6b égalité : priority le plus bas gagne, puis code alpha."""
    c1 = Coupon(
        code="B",
        type="FIXED",
        value=100,
        stackable=False,
        priority=5,
        valid_from=0,
        valid_to=100,
    )
    c2 = Coupon(
        code="A",
        type="FIXED",
        value=100,
        stackable=True,
        priority=10,
        valid_from=0,
        valid_to=100,
    )
    # même remise (100), priority 5 < 10 → c1 "B" gagne
    result = resolve_coupons(500, [c1, c2], current_day=10)
    assert result.applied_codes == ["B"]


def test_bhv6b_tie_priority_equal_code_alpha_wins():
    """BHV-6b égalité remise + priority identique → code alphabétique gagne."""
    c_z = Coupon(
        code="Z",
        type="FIXED",
        value=100,
        stackable=False,
        priority=5,
        valid_from=0,
        valid_to=100,
    )
    c_a = Coupon(
        code="A",
        type="FIXED",
        value=100,
        stackable=False,
        priority=5,
        valid_from=0,
        valid_to=100,
    )
    result = resolve_coupons(500, [c_z, c_a], current_day=10)
    assert result.applied_codes == ["A"]


def test_free_shipping_stackable_sets_flag():
    """FREE_SHIPPING ne touche pas coupon_discounts mais positionne free_shipping=True."""
    c = Coupon(
        code="FREESHIP",
        type="FREE_SHIPPING",
        value=0,
        stackable=True,
        priority=1,
        valid_from=0,
        valid_to=100,
    )
    result = resolve_coupons(1000, [c], current_day=10)
    assert result.coupon_discounts == 0
    assert result.free_shipping is True
    assert result.applied_codes == ["FREESHIP"]


def test_bhv6a_free_shipping_and_percent_combined():
    """BHV-6a : FREE_SHIPPING + PERCENT tous stackables → les deux appliqués."""
    c_pct = Coupon(
        code="PCT10",
        type="PERCENT",
        value=1000,
        stackable=True,
        priority=1,
        valid_from=0,
        valid_to=100,
    )
    c_fs = Coupon(
        code="SHIP",
        type="FREE_SHIPPING",
        value=0,
        stackable=True,
        priority=2,
        valid_from=0,
        valid_to=100,
    )
    result = resolve_coupons(1000, [c_pct, c_fs], current_day=10)
    assert result.coupon_discounts == 100
    assert result.free_shipping is True
    assert set(result.applied_codes) == {"PCT10", "SHIP"}
