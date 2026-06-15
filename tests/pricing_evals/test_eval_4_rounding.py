import pytest

from pricing.pricing import price
from pricing.tax import compute_tax


@pytest.mark.eval
def test_eval_4_halfup():
    """TVA tombant exactement sur x.5 centime arrondit à x+1 half-up (INV-7, BHV-10).

    tax_bps=550, taxable_base=100 : 100*550/10000 = 5.5 → round_half_up → 6 (pas 5).
    """
    cart = {"lines": [{"sku": "A", "qty": 1, "unit_price_cents": 100}]}
    ctx = {
        "shipping_cents": 500,
        "free_shipping_threshold_cents": 100,
        "tax_bps": 550,
        "current_day": 10,
    }
    result = price(cart, [], ctx)

    # goods_final=100, shipping=0 (franco seuil inclus, BHV-7a), taxable=100
    assert result["goods_final"] == 100
    assert result["shipping"] == 0
    assert result["tax"] == 6  # 5.5 → 6 (half-up), pas 5 (floor)


@pytest.mark.eval
def test_eval_4_no_double_rounding():
    """TVA multi-lignes == TVA calculée une seule fois sur la base totale (INV-7, BHV-10).

    Deux lignes de 5 cents, tax_bps=550 :
    - double arrondi (faux) : compute_tax(5, 550) + compute_tax(5, 550) = 0 + 0 = 0
    - arrondi unique (juste) : compute_tax(10, 550) = 1
    """
    cart = {
        "lines": [
            {"sku": "A", "qty": 1, "unit_price_cents": 5},
            {"sku": "B", "qty": 1, "unit_price_cents": 5},
        ]
    }
    ctx = {
        "shipping_cents": 0,
        "free_shipping_threshold_cents": 10000,
        "tax_bps": 550,
        "current_day": 10,
    }
    result = price(cart, [], ctx)

    total_base = result["goods_final"] + result["shipping"]
    tax_once = compute_tax(total_base, 550)
    tax_double_rounded = compute_tax(5, 550) + compute_tax(5, 550)

    assert result["tax"] == tax_once  # = 1 (arrondi unique sur base totale)
    assert tax_once != tax_double_rounded  # les deux méthodes divergent : 1 ≠ 0
    assert result["tax"] != tax_double_rounded  # pas de double arrondi
