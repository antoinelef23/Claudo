"""CLI de démo manuelle — argparse minimal, store en mémoire, temps en arguments (ADR-1)."""

import argparse
import json

from .availability import availability as compute_availability
from .store import BookingStore


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="booking",
        description="Démo manuelle du gestionnaire de réservations de salles.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_book = sub.add_parser("book", help="Réserver un créneau.")
    p_book.add_argument("--room", required=True, help="Identifiant de la salle.")
    p_book.add_argument(
        "--start", type=int, required=True, help="Début (minutes depuis minuit)."
    )
    p_book.add_argument(
        "--end", type=int, required=True, help="Fin (minutes depuis minuit)."
    )
    p_book.add_argument("--holder", required=True, help="Titulaire de la réservation.")

    p_cancel = sub.add_parser("cancel", help="Annuler une réservation.")
    p_cancel.add_argument(
        "--id", required=True, dest="booking_id", help="Identifiant de la réservation."
    )

    p_avail = sub.add_parser("availability", help="Créneaux libres d'une salle.")
    p_avail.add_argument("--room", required=True, help="Identifiant de la salle.")
    p_avail.add_argument(
        "--start",
        type=int,
        required=True,
        help="Début de la fenêtre (minutes depuis minuit).",
    )
    p_avail.add_argument(
        "--end",
        type=int,
        required=True,
        help="Fin de la fenêtre (minutes depuis minuit).",
    )

    args = parser.parse_args()
    store = BookingStore()

    if args.command == "book":
        result = store.book(args.room, args.start, args.end, args.holder)
    elif args.command == "cancel":
        result = store.cancel(args.booking_id)
    else:
        gaps = compute_availability(store, args.room, args.start, args.end)
        result = {"gaps": [list(g) for g in gaps]}

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
