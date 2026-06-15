import argparse
import sys

from repartition.core import split


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="repartition",
        description="Répartit un montant en parts entières aussi égales que possible.",
    )
    parser.add_argument(
        "--total", type=int, required=True, help="Montant entier >= 0 à répartir"
    )
    parser.add_argument("--parts", type=int, required=True, help="Nombre de parts > 0")
    args = parser.parse_args(argv)

    try:
        shares = split(args.total, args.parts)
    except ValueError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1

    print(shares)
    return 0


if __name__ == "__main__":
    sys.exit(main())
