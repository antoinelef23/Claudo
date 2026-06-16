"""EVAL-1 — Exemples EX-1..EX-5 (spec.md §6, EVAL-1). Merge gate."""

import json

import pytest
from fastapi.testclient import TestClient

from gateway.app import create_app
from gateway.store import InMemoryStore
from gateway.verify import sign

NOW = 1_700_000_000
SECRET = b"acme-test-key"
SOURCE = "acme"


@pytest.fixture(scope="module")
def store():
    return InMemoryStore()


@pytest.fixture(scope="module")
def client(store):
    app = create_app(
        secrets={SOURCE: SECRET},
        store=store,
        now=lambda: NOW,
    )
    with TestClient(app) as c:
        yield c


@pytest.mark.eval
def test_eval_1_ex1_valid_new(client, store):
    """EX-1 — BHV-1: événement valide neuf → 202, store={evt-1}."""
    event_id = "evt-1"
    raw = json.dumps(
        {"event_id": event_id, "type": "order.created", "data": {"amount": 42}}
    ).encode()
    sig = f"sha256={sign(SECRET, NOW, raw)}"
    resp = client.post(
        f"/webhooks/{SOURCE}",
        content=raw,
        headers={
            "X-Timestamp": str(NOW),
            "X-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["event_id"] == event_id
    assert store.get(event_id) is not None


@pytest.mark.eval
def test_eval_1_ex2_bad_signature(client, store):
    """EX-2 — BHV-2: signature falsifiée sha256=deadbeef → 401, store inchangé."""
    event_id = "evt-2"
    raw = json.dumps(
        {"event_id": event_id, "type": "order.created", "data": {}}
    ).encode()
    resp = client.post(
        f"/webhooks/{SOURCE}",
        content=raw,
        headers={
            "X-Timestamp": str(NOW),
            "X-Signature": "sha256=deadbeef",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 401
    assert store.get(event_id) is None


@pytest.mark.eval
def test_eval_1_ex3_stale_timestamp(client, store):
    """EX-3 — BHV-3: horodatage périmé (NOW−1000 s, hors fenêtre 300 s) → 401, store inchangé."""
    event_id = "evt-3"
    stale_ts = NOW - 1000  # −1000 s, bien au-delà du MAX_SKEW=300
    raw = json.dumps(
        {"event_id": event_id, "type": "order.created", "data": {}}
    ).encode()
    sig = f"sha256={sign(SECRET, stale_ts, raw)}"
    resp = client.post(
        f"/webhooks/{SOURCE}",
        content=raw,
        headers={
            "X-Timestamp": str(stale_ts),
            "X-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 401
    assert store.get(event_id) is None


@pytest.mark.eval
def test_eval_1_ex4_duplicate(client, store):
    """EX-4 — BHV-4: doublon de EX-1 (evt-1 déjà dans store) → 409, store inchangé."""
    event_id = "evt-1"
    raw = json.dumps(
        {"event_id": event_id, "type": "order.created", "data": {"amount": 42}}
    ).encode()
    sig = f"sha256={sign(SECRET, NOW, raw)}"
    payload_before = store.get(event_id)
    assert payload_before is not None, (
        "EX-4 requiert que EX-1 ait été exécuté en premier"
    )
    resp = client.post(
        f"/webhooks/{SOURCE}",
        content=raw,
        headers={
            "X-Timestamp": str(NOW),
            "X-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["status"] == "duplicate"
    assert body["event_id"] == event_id
    assert store.get(event_id) == payload_before


@pytest.mark.eval
def test_eval_1_ex5_read_known(client, store):
    """EX-5 — BHV-6: GET /events/evt-1 → 200 + payload."""
    resp = client.get("/events/evt-1")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["event_id"] == "evt-1"
