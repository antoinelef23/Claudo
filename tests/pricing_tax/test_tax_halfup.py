from pricing.tax import compute_tax, round_half_up


# --- round_half_up ---


def test_round_half_up_exact_half_rounds_up():
    # 5000 / 10000 = 0.5 → half-up → 1 (INV-7)
    assert round_half_up(5000, 10000) == 1


def test_round_half_up_below_half_rounds_down():
    # 4999 / 10000 = 0.4999 → rounds down → 0
    assert round_half_up(4999, 10000) == 0


def test_round_half_up_above_half_rounds_up():
    # 5001 / 10000 → rounds up → 1
    assert round_half_up(5001, 10000) == 1


def test_round_half_up_exact_integer():
    assert round_half_up(20000, 10000) == 2


def test_round_half_up_zero():
    assert round_half_up(0, 10000) == 0


def test_round_half_up_larger_multiple():
    # 15000 / 10000 = 1.5 → 2
    assert round_half_up(15000, 10000) == 2


# --- compute_tax ---


def test_compute_tax_ex2_20pct_on_2500():
    # EX-2 spec §7 : goods 2000 + shipping 500 = taxable 2500, TVA 20 % (2000 bps) = 500
    assert compute_tax(2500, 2000) == 500


def test_compute_tax_half_up_centime():
    # base=5, bps=1000 → 5*1000/10000 = 0.5 → half-up → 1 (x.5 → x+1)
    assert compute_tax(5, 1000) == 1


def test_compute_tax_below_half_rounds_down():
    # base=4, bps=1000 → 4*1000/10000 = 0.4 → rounds down → 0 (x.49 → x)
    assert compute_tax(4, 1000) == 0


def test_compute_tax_zero_base():
    assert compute_tax(0, 2000) == 0


def test_compute_tax_zero_rate():
    assert compute_tax(1000, 0) == 0


def test_compute_tax_single_rounding():
    # Vérifie qu'on arrondit UNE SEULE fois sur la base totale (pas par fraction).
    # base=15, bps=1000 → 15000/10000 = 1.5 → 2
    # Si on arrondissait base=5 et base=10 séparément : round(0.5)+round(1.0) = 1+1 = 2, même résultat ici.
    # Cas où ça divergerait : base=5+5=10, bps=1000 → round_half_up(10000,10000)=1
    # vs deux fois round_half_up(5000,10000) = 1+1 = 2 ≠ 1
    assert compute_tax(10, 1000) == 1  # 10*1000/10000 = 1.0 → 1, une seule fois
