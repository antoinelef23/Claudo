"""EVAL-3 — déterminisme & idempotence : INV-5, INV-6, BHV-9.

@pytest.mark.eval — merge gate.
(a) deux appels identiques → même ventilation
(b) permuter l'ordre du tableau coupons → même résultat (INV-5)
(c) dupliquer un coupon → même résultat qu'une occurrence (INV-6, BHV-9)
"""

import pytest

from pricing.pricing import price

_CART = {
    "lines": [
        {"sku": "A", "qty": 3, "unit_price_cents": 2000},
        {"sku": "B", "qty": 25, "unit_price_cents": 500},
    ]
}

_COUPONS = [
    {
        "code": "WELCOME10",
        "type": "PERCENT",
        "value": 1000,
        "stackable": True,
        "priority": 10,
        "valid_from": 0,
        "valid_to": 100,
    },
    {
        "code": "EXTRA5",
        "type": "PERCENT",
        "value": 500,
        "stackable": True,
        "priority": 20,
        "valid_from": 0,
        "valid_to": 100,
    },
]

_CTX = {
    "shipping_cents": 500,
    "free_shipping_threshold_cents": 5000,
    "tax_bps": 2000,
    "current_day": 10,
}


@pytest.mark.eval
def test_eval_3a_identical_calls_produce_identical_result():
    """EVAL-3a — même entrée → même ventilation."""
    r1 = price(_CART, _COUPONS, _CTX)
    r2 = price(_CART, _COUPONS, _CTX)
    assert r1 == r2


@pytest.mark.eval
def test_eval_3b_coupon_order_does_not_affect_result():
    """EVAL-3b — permuter l'ordre du tableau coupons → même résultat (INV-5)."""
    r1 = price(_CART, _COUPONS, _CTX)
    r2 = price(_CART, list(reversed(_COUPONS)), _CTX)
    assert r1 == r2


@pytest.mark.eval
def test_eval_3b_coupon_order_many_permutations():
    """EVAL-3b étendu — plusieurs permutations toutes équivalentes."""
    import itertools

    base = price(_CART, _COUPONS, _CTX)
    for perm in itertools.permutations(_COUPONS):
        assert price(_CART, list(perm), _CTX) == base, (
            f"Permutation {perm} gave different result"
        )


@pytest.mark.eval
def test_eval_3c_duplicate_coupon_same_as_single_occurrence():
    """EVAL-3c — dupliquer un coupon → même résultat qu'une occurrence (INV-6, BHV-9)."""
    single = [_COUPONS[0]]
    duplicated = [_COUPONS[0], _COUPONS[0]]
    r1 = price(_CART, single, _CTX)
    r2 = price(_CART, duplicated, _CTX)
    assert r1 == r2


@pytest.mark.eval
def test_eval_3c_duplicate_multiple_coupons():
    """EVAL-3c étendu — tous les coupons dupliqués → même résultat."""
    doubled = _COUPONS + _COUPONS
    r1 = price(_CART, _COUPONS, _CTX)
    r2 = price(_CART, doubled, _CTX)
    assert r1 == r2


@pytest.mark.eval
def test_eval_3c_applied_coupons_no_duplicates():
    """EVAL-3c — applied_coupons ne liste un code qu'une fois même si dupliqué en entrée."""
    doubled = [_COUPONS[0], _COUPONS[0]]
    result = price(_CART, doubled, _CTX)
    assert len(result["applied_coupons"]) == len(set(result["applied_coupons"]))
