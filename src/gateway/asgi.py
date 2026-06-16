"""ASGI entrypoint (Cloud Run) — câble `create_app` avec la config réelle issue de
l'environnement. Couche de déploiement (FDE), hors spec/evals : aucune règle métier ici.

Fail-closed : refuse de démarrer sans secret d'ingestion ni jeton de lecture (jamais de
défaut ouvert qui réintroduirait l'IDOR F-1). Secrets injectés par l'env (en prod : Secret
Manager → variables d'env du service), jamais en dur (INV-6, R-22).
"""

from __future__ import annotations

import os
import time

from gateway.app import create_app
from gateway.store import InMemoryStore


def _require(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"{name} requis — refus de démarrer (fail-closed)")
    return value


def _secrets() -> dict[str, bytes]:
    """`GATEWAY_SECRET_<SOURCE>` → clé HMAC de la source. Au moins une requise."""
    out: dict[str, bytes] = {}
    prefix = "GATEWAY_SECRET_"
    for key, val in os.environ.items():
        if key.startswith(prefix) and val:
            out[key[len(prefix) :].lower()] = val.encode()
    if not out:
        raise RuntimeError(
            "aucun GATEWAY_SECRET_<SOURCE> configuré — refus de démarrer"
        )
    return out


app = create_app(
    secrets=_secrets(),
    store=InMemoryStore(),
    now=lambda: int(time.time()),
    read_token=_require("GATEWAY_READ_TOKEN"),
)
