"""Tests BHV-1..7 pour l'adaptateur FastAPI (T3).

Pas d'eval ici — les evals EX-1..EX-5, EVAL-2, EVAL-3 relèvent de T4/T5/T6.
"""

import json

from fastapi.testclient import TestClient

from gateway.app import create_app
from gateway.store import InMemoryStore
from gateway.verify import sign

SECRET = b"test-secret"
SECRETS = {"acme": SECRET}
NOW = 1_700_000_000


def _make_client(
    store: InMemoryStore | None = None,
) -> tuple[TestClient, InMemoryStore]:
    if store is None:
        store = InMemoryStore()
    app = create_app(secrets=SECRETS, store=store, now=lambda: NOW)
    return TestClient(app), store


def _raw(**fields) -> bytes:
    return json.dumps(fields).encode()


def _valid_headers(raw: bytes, timestamp: int = NOW) -> dict:
    sig = sign(SECRET, timestamp, raw)
    return {"X-Timestamp": str(timestamp), "X-Signature": f"sha256={sig}"}


# --- BHV-1 : événement valide neuf → 202, magasin mis à jour ---


def test_bhv1_valid_event_202():
    client, store = _make_client()
    raw = _raw(event_id="evt-1", type="payment", data={"amount": 100})
    resp = client.post("/webhooks/acme", content=raw, headers=_valid_headers(raw))
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["event_id"] == "evt-1"
    assert store.get("evt-1") is not None


# --- BHV-2 : signature invalide → 401, rien enregistré ---


def test_bhv2_bad_signature_401():
    client, store = _make_client()
    raw = _raw(event_id="evt-2", type="payment", data={})
    headers = {"X-Timestamp": str(NOW), "X-Signature": "sha256=deadbeef"}
    resp = client.post("/webhooks/acme", content=raw, headers=headers)
    assert resp.status_code == 401
    assert store.get("evt-2") is None


def test_bhv2_missing_signature_401():
    client, store = _make_client()
    raw = _raw(event_id="evt-2b", type="payment", data={})
    resp = client.post("/webhooks/acme", content=raw, headers={"X-Timestamp": str(NOW)})
    assert resp.status_code == 401
    assert store.get("evt-2b") is None


# --- BHV-3 : horodatage périmé → 401, rien enregistré ---


def test_bhv3_stale_timestamp_401():
    client, store = _make_client()
    stale = NOW - 1000
    raw = _raw(event_id="evt-3", type="order", data={})
    resp = client.post(
        "/webhooks/acme", content=raw, headers=_valid_headers(raw, stale)
    )
    assert resp.status_code == 401
    assert store.get("evt-3") is None


def test_bhv3_future_timestamp_401():
    client, store = _make_client()
    future = NOW + 1000
    raw = _raw(event_id="evt-3b", type="order", data={})
    resp = client.post(
        "/webhooks/acme", content=raw, headers=_valid_headers(raw, future)
    )
    assert resp.status_code == 401
    assert store.get("evt-3b") is None


# --- BHV-4 : doublon → 409, magasin inchangé ---


def test_bhv4_duplicate_409():
    client, store = _make_client()
    raw = _raw(event_id="evt-dup", type="order", data={"ref": "X"})
    headers = _valid_headers(raw)
    r1 = client.post("/webhooks/acme", content=raw, headers=headers)
    assert r1.status_code == 202
    snapshot = store.get("evt-dup")
    r2 = client.post("/webhooks/acme", content=raw, headers=headers)
    assert r2.status_code == 409
    body = r2.json()
    assert body["status"] == "duplicate"
    assert body["event_id"] == "evt-dup"
    assert store.get("evt-dup") == snapshot


# --- BHV-5 : healthz → 200 {"status":"ok"} ---


def test_bhv5_healthz():
    client, _ = _make_client()
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# --- BHV-6 : relecture → 200 + payload si connu, 404 sinon ---


def test_bhv6_get_known_event_200():
    client, store = _make_client()
    raw = _raw(event_id="evt-lookup", type="test", data={"x": 1})
    client.post("/webhooks/acme", content=raw, headers=_valid_headers(raw))
    resp = client.get("/events/evt-lookup")
    assert resp.status_code == 200
    assert resp.json()["event_id"] == "evt-lookup"


def test_bhv6_get_unknown_event_404():
    client, _ = _make_client()
    resp = client.get("/events/no-such-event")
    assert resp.status_code == 404


# --- BHV-7 : corps malformé → 400, rien enregistré ---


def test_bhv7_invalid_json_400():
    client, store = _make_client()
    raw = b"not valid json {"
    resp = client.post("/webhooks/acme", content=raw, headers=_valid_headers(raw))
    assert resp.status_code == 400
    assert store.get("any-id") is None


def test_bhv7_missing_event_id_400():
    client, store = _make_client()
    raw = _raw(type="order", data={})
    resp = client.post("/webhooks/acme", content=raw, headers=_valid_headers(raw))
    assert resp.status_code == 400
    assert store.get("anything") is None


def test_bhv7_missing_type_400():
    client, store = _make_client()
    raw = _raw(event_id="evt-x", data={})
    resp = client.post("/webhooks/acme", content=raw, headers=_valid_headers(raw))
    assert resp.status_code == 400


def test_bhv7_missing_data_400():
    client, store = _make_client()
    raw = _raw(event_id="evt-y", type="order")
    resp = client.post("/webhooks/acme", content=raw, headers=_valid_headers(raw))
    assert resp.status_code == 400


# --- Source inconnue → 401 (même réponse que signature invalide, INV-6) ---


def test_unknown_source_401():
    client, store = _make_client()
    raw = _raw(event_id="evt-z", type="test", data={})
    headers = {"X-Timestamp": str(NOW), "X-Signature": "sha256=abc123"}
    resp = client.post("/webhooks/unknown-source", content=raw, headers=headers)
    assert resp.status_code == 401
    assert store.get("evt-z") is None
