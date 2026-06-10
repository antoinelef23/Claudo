"""Evals du module calc — spec devis-pose §7 (EVAL-1, EVAL-2)."""

import pytest

from devis.calc import compute_quote

# EX-1, EX-2, EX-3 — spec.md §5, vérifiés à l'euro près (EVAL-1)
EXAMPLES = [
    pytest.param(
        {"products_subtotal_eur": 1500.00, "surface_m2": 10},
        {
            "products_eur": 1500.00,
            "installation_eur": 450.00,
            "total_eur": 1950.00,
            "is_estimate": True,
        },
        id="ex-1-nominal-sans-remise",
    ),
    pytest.param(
        {"products_subtotal_eur": 2500.00, "surface_m2": 20},
        {
            "products_eur": 2375.00,
            "installation_eur": 900.00,
            "total_eur": 3275.00,
            "is_estimate": True,
        },
        id="ex-2-remise-volume-pose-intacte",
    ),
    pytest.param(
        {"products_subtotal_eur": 100.00, "surface_m2": 0},
        {"total_eur": 100.00},
        id="ex-3-surface-nulle",
    ),
]


@pytest.mark.eval
@pytest.mark.parametrize(("inputs", "expected"), EXAMPLES)
def test_eval_1_exemples_exacts(inputs: dict, expected: dict) -> None:
    quote = compute_quote(**inputs)
    for key, value in expected.items():
        if isinstance(value, bool):
            assert quote[key] is value
        else:
            assert quote[key] == pytest.approx(value, abs=0.5)  # à l'euro près


def _grille() -> list[tuple[float, float]]:
    # EVAL-2 : montants 0→10⁶, surfaces 0→500, plus les bords métier
    # (seuil de remise BHV-2/BHV-2a, surface nulle BHV-1a).
    montants = [i * 1_000_000 / 40 for i in range(41)]
    montants += [0.01, 1999.99, 2000.00, 2000.01, 2050.55]
    surfaces = [i * 500 / 20 for i in range(21)]
    surfaces += [0.5, 12.34]
    return [(m, s) for m in montants for s in surfaces]


@pytest.mark.eval
@pytest.mark.parametrize(("montant", "surface"), _grille())
def test_eval_2_proprietes(montant: float, surface: float) -> None:
    quote = compute_quote(montant, surface)
    assert quote["total_eur"] >= 0  # INV-1
    assert quote["is_estimate"] is True  # INV-2
