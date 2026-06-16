"""EVAL-2 — property idempotence (INV-4, T5).

500 séquences aléatoires (seed=42) : pool de 100 event_id distincts tirés
au sort avec répétition — garantit un mélange de premières livraisons et de
doublons. Chaque livraison est signée+fraîche (now figé). Vérifie INV-4 :
- première livraison d'un id → 202 ;
- toute livraison ultérieure du même id → 409, magasin inchangé ;
- à la fin, le magasin contient EXACTEMENT l'ensemble des id distincts envoyés.
"""

import json
import random

import pytest
from fastapi.testclient import TestClient

from gateway.app import create_app
from gateway.store import InMemoryStore
from gateway.verify import sign

_SECRET = b"acme-test-key"
_SECRETS = {"acme": _SECRET}
_NOW = 1_700_000_000
_N = 500
_POOL_SIZE = 100


@pytest.mark.eval
def test_eval_2_idempotence() -> None:
    store = InMemoryStore()
    app = create_app(secrets=_SECRETS, store=store, now=lambda: _NOW)
    client = TestClient(app)

    rng = random.Random(42)
    pool = [f"evt-{i}" for i in range(_POOL_SIZE)]

    seen: set[str] = set()
    all_ids: list[str] = []

    for _ in range(_N):
        event_id = rng.choice(pool)
        all_ids.append(event_id)

        raw = json.dumps({"event_id": event_id, "type": "test", "data": {}}).encode()
        sig = f"sha256={sign(_SECRET, _NOW, raw)}"

        is_first = event_id not in seen
        snapshot_before = dict(store._store)

        resp = client.post(
            "/webhooks/acme",
            content=raw,
            headers={
                "X-Timestamp": str(_NOW),
                "X-Signature": sig,
                "Content-Type": "application/json",
            },
        )

        if is_first:
            seen.add(event_id)
            assert resp.status_code == 202, (
                f"Première livraison de {event_id!r} : attendu 202, reçu {resp.status_code}"
            )
        else:
            assert resp.status_code == 409, (
                f"Doublon de {event_id!r} : attendu 409, reçu {resp.status_code}"
            )
            # INV-4 : aucun effet de bord — magasin strictement inchangé
            assert store._store == snapshot_before, (
                f"Le magasin a changé après livraison en doublon de {event_id!r} (INV-4 violé)"
            )

    # INV-4 vérification finale : le magasin contient EXACTEMENT les id distincts
    distinct_ids = set(all_ids)
    assert set(store._store.keys()) == distinct_ids, (
        f"Clés du magasin {set(store._store.keys())} ≠ id distincts {distinct_ids}"
    )
    # Sanité : seed=42 + pool=100 + N=500 doit produire à la fois des premières et des doublons
    assert len(distinct_ids) < _N, "Aucun doublon généré — seed/pool mal configuré"
    assert len(distinct_ids) > 1, "Un seul id distinct — seed/pool mal configuré"
