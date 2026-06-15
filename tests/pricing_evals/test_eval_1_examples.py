"""EVAL-1 — déterministe : EX-1 à EX-9 de spec.md §7 vérifiés exactement.

@pytest.mark.eval — merge gate (100 % requis).
Contexte par défaut : shipping_cents=500, free_shipping_threshold_cents=5000,
tax_bps=2000 (20 %), current_day=10 — sauf override explicite d'exemple.
"""

import pytest

from pricing.pricing import price

DEFAULT_CTX = {
    "shipping_cents": 500,
    "free_shipping_threshold_cents": 5000,
    "tax_bps": 2000,
    "current_day": 10,
}


@pytest.mark.eval
def test_eval_1_ex1_panier_vide():
    """EX-1 — BHV-1 : panier vide → ventilation toute à zéro, aucun port."""
    result = price({"lines": []}, [], DEFAULT_CTX)
    assert result == {
        "goods_subtotal": 0,
        "line_discounts": 0,
        "coupon_discounts": 0,
        "goods_final": 0,
        "shipping": 0,
        "tax": 0,
        "total": 0,
        "applied_coupons": [],
    }


@pytest.mark.eval
def test_eval_1_ex2_ligne_simple():
    """EX-2 — BHV-2/BHV-10/BHV-11 : une ligne qty<20, aucun coupon.

    goods 2000 ; port 500 (2000<5000) ; taxable 2500 ; TVA 500 ; total 3000.
    """
    result = price(
        {"lines": [{"sku": "A", "qty": 2, "unit_price_cents": 1000}]},
        [],
        DEFAULT_CTX,
    )
    assert result == {
        "goods_subtotal": 2000,
        "line_discounts": 0,
        "coupon_discounts": 0,
        "goods_final": 2000,
        "shipping": 500,
        "tax": 500,
        "total": 3000,
        "applied_coupons": [],
    }


@pytest.mark.eval
def test_eval_1_ex3_palier_5pct_qty20_franco():
    """EX-3 — BHV-3/BHV-3a/BHV-7 : palier 5 % à qty=20 inclus + franco.

    goods 20000 ; remise ligne 1000 (5 %) ; goods_final 19000 ;
    franco (19000>=5000) → port 0 ; TVA 3800 ; total 22800.
    """
    result = price(
        {"lines": [{"sku": "A", "qty": 20, "unit_price_cents": 1000}]},
        [],
        DEFAULT_CTX,
    )
    assert result == {
        "goods_subtotal": 20000,
        "line_discounts": 1000,
        "coupon_discounts": 0,
        "goods_final": 19000,
        "shipping": 0,
        "tax": 3800,
        "total": 22800,
        "applied_coupons": [],
    }


@pytest.mark.eval
def test_eval_1_ex4_palier_10pct_qty50():
    """EX-4 — BHV-3b/BHV-7 : palier 10 % à qty=50 inclus.

    goods 50000 ; remise ligne 5000 (10 %) ; goods_final 45000 ;
    franco ; TVA 9000 ; total 54000.
    """
    result = price(
        {"lines": [{"sku": "A", "qty": 50, "unit_price_cents": 1000}]},
        [],
        DEFAULT_CTX,
    )
    assert result == {
        "goods_subtotal": 50000,
        "line_discounts": 5000,
        "coupon_discounts": 0,
        "goods_final": 45000,
        "shipping": 0,
        "tax": 9000,
        "total": 54000,
        "applied_coupons": [],
    }


@pytest.mark.eval
def test_eval_1_ex5_coupon_percent_cumulable():
    """EX-5 — BHV-4 : coupon PERCENT cumulable (WELCOME10, 10 %).

    goods 2000 ; coupon 10 % = 200 ; goods_final 1800 ; port 500 ;
    taxable 2300 ; TVA 460 ; total 2760.
    """
    coupons = [
        {
            "code": "WELCOME10",
            "type": "PERCENT",
            "value": 1000,
            "stackable": True,
            "priority": 10,
            "valid_from": 0,
            "valid_to": 100,
        }
    ]
    result = price(
        {"lines": [{"sku": "A", "qty": 2, "unit_price_cents": 1000}]},
        coupons,
        DEFAULT_CTX,
    )
    assert result == {
        "goods_subtotal": 2000,
        "line_discounts": 0,
        "coupon_discounts": 200,
        "goods_final": 1800,
        "shipping": 500,
        "tax": 460,
        "total": 2760,
        "applied_coupons": ["WELCOME10"],
    }


@pytest.mark.eval
def test_eval_1_ex6_coupon_fixed_plafonne():
    """EX-6 — BHV-5/BHV-11 : FIXED plafonné (value > marchandise), total > 0.

    goods 500 ; FIXED 99999 plafonné à 500 ; goods_final 0 ;
    port 500 (0<5000) ; taxable 500 ; TVA 100 ; total 600.
    """
    coupons = [
        {
            "code": "BIG",
            "type": "FIXED",
            "value": 99999,
            "stackable": True,
            "priority": 5,
            "valid_from": 0,
            "valid_to": 100,
        }
    ]
    result = price(
        {"lines": [{"sku": "A", "qty": 1, "unit_price_cents": 500}]},
        coupons,
        DEFAULT_CTX,
    )
    assert result == {
        "goods_subtotal": 500,
        "line_discounts": 0,
        "coupon_discounts": 500,
        "goods_final": 0,
        "shipping": 500,
        "tax": 100,
        "total": 600,
        "applied_coupons": ["BIG"],
    }


@pytest.mark.eval
def test_eval_1_ex7_exclusif_bat_cumulable():
    """EX-7 — BHV-6/BHV-6b : coupon exclusif présent → seule la meilleure remise unique s'applique.

    goods 10000 ; EXCL20 (2000) > STACK5 (500) → EXCL20 retenu ;
    goods_final 8000 ; franco (8000>=5000) ; TVA 1600 ; total 9600.
    """
    coupons = [
        {
            "code": "STACK5",
            "type": "PERCENT",
            "value": 500,
            "stackable": True,
            "priority": 10,
            "valid_from": 0,
            "valid_to": 100,
        },
        {
            "code": "EXCL20",
            "type": "PERCENT",
            "value": 2000,
            "stackable": False,
            "priority": 20,
            "valid_from": 0,
            "valid_to": 100,
        },
    ]
    result = price(
        {"lines": [{"sku": "A", "qty": 2, "unit_price_cents": 5000}]},
        coupons,
        DEFAULT_CTX,
    )
    assert result == {
        "goods_subtotal": 10000,
        "line_discounts": 0,
        "coupon_discounts": 2000,
        "goods_final": 8000,
        "shipping": 0,
        "tax": 1600,
        "total": 9600,
        "applied_coupons": ["EXCL20"],
    }


@pytest.mark.eval
def test_eval_1_ex8_coupon_expire_ignore():
    """EX-8 — BHV-8 : coupon expiré (valid_to=5, current_day=10) → ignoré.

    goods 1000 ; port 500 ; TVA 300 ; total 1800.
    """
    coupons = [
        {
            "code": "OLD",
            "type": "PERCENT",
            "value": 5000,
            "stackable": True,
            "priority": 1,
            "valid_from": 0,
            "valid_to": 5,
        }
    ]
    result = price(
        {"lines": [{"sku": "A", "qty": 1, "unit_price_cents": 1000}]},
        coupons,
        DEFAULT_CTX,
    )
    assert result == {
        "goods_subtotal": 1000,
        "line_discounts": 0,
        "coupon_discounts": 0,
        "goods_final": 1000,
        "shipping": 500,
        "tax": 300,
        "total": 1800,
        "applied_coupons": [],
    }


@pytest.mark.eval
def test_eval_1_ex9_free_shipping_independant_coupon_exclusif():
    """EX-9 — BHV-6c : FREE_SHIPPING indépendant du cumul marchandise.

    Contexte override : free_shipping_threshold_cents=50000 (franco hors atteinte).
    EXCL20 exclusif appliqué (remise marchandise) ; LIVRAISON FREE_SHIPPING
    accordé indépendamment → port 0.
    goods_final 8000 ; port 0 ; TVA 1600 ; total 9600 ;
    applied_coupons ordre canonique (priority 5 → 20) : ["LIVRAISON", "EXCL20"].
    """
    ctx = {
        "shipping_cents": 500,
        "free_shipping_threshold_cents": 50000,
        "tax_bps": 2000,
        "current_day": 10,
    }
    coupons = [
        {
            "code": "LIVRAISON",
            "type": "FREE_SHIPPING",
            "value": 0,
            "stackable": True,
            "priority": 5,
            "valid_from": 0,
            "valid_to": 100,
        },
        {
            "code": "EXCL20",
            "type": "PERCENT",
            "value": 2000,
            "stackable": False,
            "priority": 20,
            "valid_from": 0,
            "valid_to": 100,
        },
    ]
    result = price(
        {"lines": [{"sku": "A", "qty": 2, "unit_price_cents": 5000}]},
        coupons,
        ctx,
    )
    assert result == {
        "goods_subtotal": 10000,
        "line_discounts": 0,
        "coupon_discounts": 2000,
        "goods_final": 8000,
        "shipping": 0,
        "tax": 1600,
        "total": 9600,
        "applied_coupons": ["LIVRAISON", "EXCL20"],
    }
