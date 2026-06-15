from pricing.model import Line
from pricing.tiers import line_discount, tier_bps


class TestTierBps:
    def test_below_first_threshold_returns_zero(self):
        assert tier_bps(19) == 0

    def test_first_threshold_inclusive_returns_500(self):
        # BHV-3a : qty == 20 → palier 5 % inclus
        assert tier_bps(20) == 500

    def test_between_thresholds_returns_500(self):
        assert tier_bps(49) == 500

    def test_second_threshold_inclusive_returns_1000(self):
        # BHV-3b : qty == 50 → palier 10 % inclus
        assert tier_bps(50) == 1000

    def test_above_second_threshold_returns_1000(self):
        assert tier_bps(100) == 1000

    def test_zero_qty_returns_zero(self):
        assert tier_bps(0) == 0


class TestLineDiscount:
    def test_no_discount_below_threshold(self):
        # qty=19 → bps=0 → remise=0
        assert line_discount(Line(sku="A", qty=19, unit_price_cents=1000)) == 0

    def test_five_percent_at_qty_20_inclusive(self):
        # 20 * 1000 = 20000 ; 20000 * 500 // 10000 = 1000  (BHV-3a)
        assert line_discount(Line(sku="A", qty=20, unit_price_cents=1000)) == 1000

    def test_five_percent_at_qty_49(self):
        # 49 * 1000 = 49000 ; 49000 * 500 // 10000 = 2450
        assert line_discount(Line(sku="A", qty=49, unit_price_cents=1000)) == 2450

    def test_ten_percent_at_qty_50_inclusive(self):
        # 50 * 1000 = 50000 ; 50000 * 1000 // 10000 = 5000  (BHV-3b)
        assert line_discount(Line(sku="A", qty=50, unit_price_cents=1000)) == 5000

    def test_truncation_floor_not_round(self):
        # qty=21, unit_price=3 → gross=63 ; 63 * 500 // 10000 = 31500 // 10000 = 3
        # 5 % de 63 = 3.15 → tronqué à 3, pas arrondi à 3 (ADR-1)
        assert line_discount(Line(sku="X", qty=21, unit_price_cents=3)) == 3
