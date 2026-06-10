"""Entrée CLI du devis de pose — enchaîne compute_quote puis format_quote (design.md §1)."""

import argparse

from devis.calc import compute_quote
from devis.format import format_quote


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="devis",
        description="Devis de pose salle de bain — estimation non contractuelle.",
    )
    parser.add_argument(
        "--products-eur",
        type=float,
        required=True,
        help="Sous-total produits du panier, en euros",
    )
    parser.add_argument(
        "--surface-m2",
        type=float,
        required=True,
        help="Surface de pose, en m²",
    )
    args = parser.parse_args(argv)

    quote = compute_quote(args.products_eur, args.surface_m2)
    print(format_quote(quote))


if __name__ == "__main__":
    main()
