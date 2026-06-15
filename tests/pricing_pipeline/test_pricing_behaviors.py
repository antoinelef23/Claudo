"""Tests comportementaux de pricing.price : BHV-1, BHV-2, BHV-7, BHV-7a."""

from pricing.pricing import price

DEFAULT_CTX = {
    "shipping_cents": 500,
    "free_shipping_threshold_cents": 5000,
    "tax_bps": 2000,
    "current_day": 10,
}


class TestBhv1PanierVide:
    """BHV-1 — panier vide : ventilation toute à zéro, aucun port."""

    def test_empty_cart_returns_all_zeros(self):
        result = price({"lines": []}, [], DEFAULT_CTX)
        assert result["goods_subtotal"] == 0
        assert result["line_discounts"] == 0
        assert result["coupon_discounts"] == 0
        assert result["goods_final"] == 0
        assert result["shipping"] == 0
        assert result["tax"] == 0
        assert result["total"] == 0
        assert result["applied_coupons"] == []

    def test_empty_cart_with_coupons_still_zero(self):
        coupon = {
            "code": "X10",
            "type": "PERCENT",
            "value": 1000,
            "stackable": True,
            "priority": 1,
            "valid_from": 0,
            "valid_to": 100,
        }
        result = price({"lines": []}, [coupon], DEFAULT_CTX)
        assert result["total"] == 0
        assert result["shipping"] == 0
        assert result["applied_coupons"] == []


class TestBhv2LigneSimple:
    """BHV-2 — ligne simple sans promotion."""

    def test_single_line_no_coupon_below_tier(self):
        # qty=2 < 20 → pas de remise de ligne
        result = price(
            {"lines": [{"sku": "A", "qty": 2, "unit_price_cents": 1000}]},
            [],
            DEFAULT_CTX,
        )
        assert result["goods_subtotal"] == 2000
        assert result["line_discounts"] == 0
        assert result["coupon_discounts"] == 0
        assert result["goods_final"] == 2000
        # goods_final 2000 < 5000 → port facturé
        assert result["shipping"] == 500
        # taxable = 2000 + 500 = 2500 ; TVA 20% = 500
        assert result["tax"] == 500
        assert result["total"] == 3000
        assert result["applied_coupons"] == []

    def test_output_has_all_keys(self):
        result = price(
            {"lines": [{"sku": "B", "qty": 1, "unit_price_cents": 200}]},
            [],
            DEFAULT_CTX,
        )
        expected_keys = {
            "goods_subtotal",
            "line_discounts",
            "coupon_discounts",
            "goods_final",
            "shipping",
            "tax",
            "total",
            "applied_coupons",
        }
        assert set(result.keys()) == expected_keys

    def test_all_values_are_int(self):
        result = price(
            {"lines": [{"sku": "C", "qty": 3, "unit_price_cents": 500}]},
            [],
            DEFAULT_CTX,
        )
        for key, val in result.items():
            if key != "applied_coupons":
                assert isinstance(val, int), f"{key} must be int, got {type(val)}"


class TestBhv7PortEtFranco:
    """BHV-7 — port et franco de port."""

    def test_goods_below_threshold_port_charged(self):
        # goods_final 4999 < 5000 → port dû
        result = price(
            {"lines": [{"sku": "A", "qty": 1, "unit_price_cents": 4999}]},
            [],
            DEFAULT_CTX,
        )
        assert result["shipping"] == 500

    def test_goods_above_threshold_free_shipping(self):
        # goods_final 5001 > 5000 → franco
        result = price(
            {"lines": [{"sku": "A", "qty": 1, "unit_price_cents": 5001}]},
            [],
            DEFAULT_CTX,
        )
        assert result["shipping"] == 0

    def test_bhv7a_goods_exact_threshold_free_shipping(self):
        """BHV-7a — seuil exact inclus : franco."""
        result = price(
            {"lines": [{"sku": "A", "qty": 1, "unit_price_cents": 5000}]},
            [],
            DEFAULT_CTX,
        )
        assert result["shipping"] == 0

    def test_free_shipping_coupon_waives_port(self):
        # goods_final 1000 < 5000 mais FREE_SHIPPING valide → port 0
        coupon = {
            "code": "FREESHIP",
            "type": "FREE_SHIPPING",
            "value": 0,
            "stackable": True,
            "priority": 1,
            "valid_from": 0,
            "valid_to": 100,
        }
        result = price(
            {"lines": [{"sku": "A", "qty": 1, "unit_price_cents": 1000}]},
            [coupon],
            DEFAULT_CTX,
        )
        assert result["shipping"] == 0
        assert "FREESHIP" in result["applied_coupons"]

    def test_expired_free_shipping_coupon_charges_port(self):
        # coupon FREE_SHIPPING expiré (BHV-8) → port dû
        coupon = {
            "code": "OLDSHIP",
            "type": "FREE_SHIPPING",
            "value": 0,
            "stackable": True,
            "priority": 1,
            "valid_from": 0,
            "valid_to": 5,  # current_day=10 > 5 → expiré
        }
        result = price(
            {"lines": [{"sku": "A", "qty": 1, "unit_price_cents": 1000}]},
            [coupon],
            DEFAULT_CTX,
        )
        assert result["shipping"] == 500
        assert result["applied_coupons"] == []


class TestReconciliation:
    """INV-3 — réconciliation total == goods_final + shipping + tax."""

    def test_reconciliation_simple(self):
        result = price(
            {"lines": [{"sku": "A", "qty": 2, "unit_price_cents": 1000}]},
            [],
            DEFAULT_CTX,
        )
        assert (
            result["total"]
            == result["goods_final"] + result["shipping"] + result["tax"]
        )

    def test_reconciliation_with_coupon_and_tier(self):
        coupon = {
            "code": "P10",
            "type": "PERCENT",
            "value": 1000,
            "stackable": True,
            "priority": 1,
            "valid_from": 0,
            "valid_to": 100,
        }
        result = price(
            {"lines": [{"sku": "A", "qty": 20, "unit_price_cents": 1000}]},
            [coupon],
            DEFAULT_CTX,
        )
        assert (
            result["total"]
            == result["goods_final"] + result["shipping"] + result["tax"]
        )
