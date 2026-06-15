def round_half_up(numerator: int, denominator: int) -> int:
    return (numerator + denominator // 2) // denominator


def compute_tax(taxable_base_cents: int, tax_bps: int) -> int:
    return round_half_up(taxable_base_cents * tax_bps, 10000)
