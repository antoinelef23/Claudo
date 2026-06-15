"""CLI de démo manuelle : panier + coupons en JSON → ventilation affichée.

Usage:
  PYTHONPATH=src uv run python -m pricing.cli --current-day 10 \\
    --cart '{"lines":[{"sku":"A","qty":2,"unit_price_cents":1000}]}' \\
    --coupons '[{"code":"WELCOME10","type":"PERCENT","value":1000,"stackable":true,"priority":10,"valid_from":0,"valid_to":100}]'

Le panier peut aussi être lu depuis stdin (--cart - ou --cart absent).
"""

from __future__ import annotations

import argparse
import json
import sys

from pricing.pricing import price


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m pricing.cli",
        description=(
            "Calcule la ventilation de prix d'un panier (démo manuelle). "
            "Tous les montants sont en centimes, les taux en bps (1 %% = 100 bps)."
        ),
    )
    p.add_argument(
        "--cart",
        metavar="JSON",
        help=(
            'Panier en JSON, ex: \'{"lines":[{"sku":"A","qty":2,"unit_price_cents":1000}]}\'. '
            'Lit stdin si absent ou "-".'
        ),
    )
    p.add_argument(
        "--coupons",
        metavar="JSON",
        default="[]",
        help="Liste de coupons en JSON (défaut : []).",
    )
    p.add_argument(
        "--current-day",
        type=int,
        required=True,
        metavar="INT",
        help="Indice de jour entier (INV-5 : déterminisme, jamais now()).",
    )
    p.add_argument(
        "--shipping",
        type=int,
        default=500,
        metavar="CENTS",
        help="Frais de port en centimes (défaut : 500).",
    )
    p.add_argument(
        "--free-shipping-threshold",
        type=int,
        default=5000,
        metavar="CENTS",
        help="Seuil de franco en centimes (défaut : 5000).",
    )
    p.add_argument(
        "--tax-bps",
        type=int,
        default=2000,
        metavar="BPS",
        help="Taux de TVA en bps (défaut : 2000 = 20 %%).",
    )
    return p


def _print_breakdown(breakdown: dict) -> None:
    w = 26
    sep = "─" * 42
    print(sep)
    print(f"  {'goods_subtotal':<{w}} {breakdown['goods_subtotal']:>8} ¢")
    print(f"  {'- line_discounts':<{w}} {breakdown['line_discounts']:>8} ¢")
    print(f"  {'- coupon_discounts':<{w}} {breakdown['coupon_discounts']:>8} ¢")
    print(f"  {'= goods_final':<{w}} {breakdown['goods_final']:>8} ¢")
    print(f"  {'+ shipping':<{w}} {breakdown['shipping']:>8} ¢")
    print(f"  {'+ tax':<{w}} {breakdown['tax']:>8} ¢")
    print(sep)
    print(f"  {'TOTAL':<{w}} {breakdown['total']:>8} ¢")
    applied = breakdown["applied_coupons"]
    if applied:
        print(f"  applied_coupons : {applied}")
    print(sep)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    cart_src = args.cart
    if cart_src is None or cart_src == "-":
        cart_src = sys.stdin.read()
    cart = json.loads(cart_src)

    coupons = json.loads(args.coupons)

    context = {
        "shipping_cents": args.shipping,
        "free_shipping_threshold_cents": args.free_shipping_threshold,
        "tax_bps": args.tax_bps,
        "current_day": args.current_day,
    }

    breakdown = price(cart, coupons, context)
    _print_breakdown(breakdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
