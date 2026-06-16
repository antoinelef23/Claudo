"""Démo manuelle de livraison de webhook (transport simulé).

Invocation : PYTHONPATH=src uv run python -m webhooks.cli --help
"""

import argparse

from webhooks.engine import deliver
from webhooks.model import Delivery, Event, Subscription
from webhooks.store import DeliveryStore
from webhooks.transport import FakeTransport


def _parse_results(tokens: list[str]) -> list[bool]:
    mapping = {
        "t": True,
        "true": True,
        "1": True,
        "f": False,
        "false": False,
        "0": False,
    }
    parsed = []
    for token in tokens:
        key = token.lower()
        if key not in mapping:
            raise ValueError(f"Token inconnu : {token!r} — utilisez T/F ou true/false")
        parsed.append(mapping[key])
    return parsed


def run(
    results: list[bool],
    url: str = "https://example.com/hook",
    secret: str = "demo-secret",
    max_attempts: int = 3,
    payload: str = "{}",
    event_id: str = "e1",
    sub_id: str = "s1",
    base_ms: int = 1000,
    cap_ms: int = 60000,
) -> tuple[Delivery, FakeTransport]:
    """Exécute une livraison complète avec un transport simulé.

    Retourne (delivery, transport) ; transport.calls permet de compter les appels.
    Horloge logique injectée — aucun now(), aucun réseau réel (INV-7).
    """
    transport = FakeTransport(results)
    sub = Subscription(id=sub_id, url=url, secret=secret, max_attempts=max_attempts)
    event = Event(id=event_id, payload=payload)
    store = DeliveryStore()

    tick = [0]

    def clock() -> int:
        tick[0] += 1000
        return tick[0]

    delivery = deliver(store, transport, sub, event, clock, base_ms, cap_ms)
    return delivery, transport


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m webhooks.cli",
        description=(
            "Démo manuelle de livraison de webhook.\n"
            "Simule un abonné, un événement et une séquence de résultats de transport."
        ),
    )
    parser.add_argument(
        "--results",
        nargs="+",
        default=["T"],
        metavar="T|F",
        help="Séquence de résultats du transport simulé (T=succès, F=échec). Ex : --results T F F",
    )
    parser.add_argument(
        "--url", default="https://example.com/hook", help="URL de l'abonné"
    )
    parser.add_argument(
        "--secret", default="demo-secret", help="Secret HMAC de l'abonné"
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        metavar="N",
        help="Nombre max de tentatives (défaut : 3)",
    )
    parser.add_argument("--payload", default="{}", help="Payload de l'événement (JSON)")
    parser.add_argument("--event-id", default="e1", help="Identifiant de l'événement")
    parser.add_argument("--sub-id", default="s1", help="Identifiant de l'abonné")
    parser.add_argument(
        "--base-ms",
        type=int,
        default=1000,
        metavar="MS",
        help="Base du backoff en ms (défaut : 1000)",
    )
    parser.add_argument(
        "--cap-ms",
        type=int,
        default=60000,
        metavar="MS",
        help="Cap du backoff en ms (défaut : 60000)",
    )

    args = parser.parse_args(argv)
    results = _parse_results(args.results)

    delivery, transport = run(
        results=results,
        url=args.url,
        secret=args.secret,
        max_attempts=args.max_attempts,
        payload=args.payload,
        event_id=args.event_id,
        sub_id=args.sub_id,
        base_ms=args.base_ms,
        cap_ms=args.cap_ms,
    )

    print(f"état final    : {delivery.state}")
    print(f"appels transport : {len(transport.calls)}")


if __name__ == "__main__":
    main()
