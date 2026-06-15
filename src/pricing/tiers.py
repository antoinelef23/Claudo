from __future__ import annotations

from pricing.model import TIER_SCHEDULE, Line


def tier_bps(qty: int) -> int:
    for qty_min, bps in TIER_SCHEDULE:
        if qty >= qty_min:
            return bps
    return 0


def line_discount(line: Line) -> int:
    return line.qty * line.unit_price_cents * tier_bps(line.qty) // 10000
