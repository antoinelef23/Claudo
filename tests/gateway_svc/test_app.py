"""Tests BHV-1..8, INV-7 pour l'adaptateur FastAPI (T3 amendé 1.1.0).

Pas d'eval ici — les evals EX-1..EX-6, EVAL-2, EVAL-3 relèvent de T4/T5/T6.
"""

import json

from fastapi.testclient import TestClient

from gateway.app import MAX_BODY, create_app
from gateway.store import InMemoryStore
from gateway.verify import sign

SECRET = b"test-secret"
SECRETS = {"acme": SECRET}
NOW = 1_700_000_000
READ_TOKEN = "read-test-token"


def _make_client(
    store: InMemoryStore | None = None,
) -> tuple[TestClient, InMemoryStore]:
    if store is None:
        store = InMemoryStore()
    app = create_app(
        secrets=SECRETS, store=store, now=lambda: NOW, read_token=READ_TOKEN
    )
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


def test_bhv2_nonhex_signature_401():
    """F-2/ADR-4: signature non-hexadécimale → 401, jamais 500."""
    client, store = _make_client()
    raw = _raw(event_id="evt-2c", type="payment", data={})
    headers = {"X-Timestamp": str(NOW), "X-Signature": "sha256=xyz!!not-hex"}
    resp = client.post("/webhooks/acme", content=raw, headers=headers)
    assert resp.status_code == 401
    assert store.get("evt-2c") is None


def test_bhv2_nonascii_signature_401():
    """F-2/ADR-4: signature avec octets non-ASCII → 401, jamais 500 (compare_digest TypeError)."""
    client, store = _make_client()
    raw = _raw(event_id="evt-2d", type="payment", data={})
    # Octets non-ASCII (0x80-0xFF) envoyés en BYTES : httpx refuse d'encoder un str non-ASCII
    # côté client. Starlette les décode latin-1 → str non-ASCII côté app, ce qui ferait lever
    # TypeError à compare_digest sans la garde F-2 (→ 500). Avec la garde : 401.
    headers = {"X-Timestamp": str(NOW), "X-Signature": b"sha256=\x80\xff\xfe"}
    resp = client.post("/webhooks/acme", content=raw, headers=headers)
    assert resp.status_code == 401
    assert store.get("evt-2d") is None


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


# --- BHV-5 : health → 200 {"status":"ok"} ---


def test_bhv5_health():
    client, _ = _make_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# --- BHV-6 / INV-7 : relecture authentifiée (amendement 1.1.0, F-1) ---


def test_bhv6_get_known_event_200():
    client, store = _make_client()
    raw = _raw(event_id="evt-lookup", type="test", data={"x": 1})
    client.post("/webhooks/acme", content=raw, headers=_valid_headers(raw))
    resp = client.get("/events/evt-lookup", headers={"X-Read-Token": READ_TOKEN})
    assert resp.status_code == 200
    assert resp.json()["event_id"] == "evt-lookup"


def test_bhv6_get_unknown_event_404():
    client, _ = _make_client()
    resp = client.get("/events/no-such-event", headers={"X-Read-Token": READ_TOKEN})
    assert resp.status_code == 404


def test_bhv6_get_without_token_401():
    """INV-7/F-1: GET sans X-Read-Token → 401, aucun payload (IDOR fermé)."""
    client, store = _make_client()
    raw = _raw(event_id="evt-auth", type="test", data={"secret": "value"})
    client.post("/webhooks/acme", content=raw, headers=_valid_headers(raw))
    resp = client.get("/events/evt-auth")
    assert resp.status_code == 401


def test_bhv6_get_with_wrong_token_401():
    """INV-7/F-1: GET avec token invalide → 401, aucun payload."""
    client, store = _make_client()
    raw = _raw(event_id="evt-auth2", type="test", data={})
    client.post("/webhooks/acme", content=raw, headers=_valid_headers(raw))
    resp = client.get("/events/evt-auth2", headers={"X-Read-Token": "wrong-token"})
    assert resp.status_code == 401


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


# --- BHV-8 : corps trop volumineux → 413 avant tout HMAC (amendement 1.1.0, F-3) ---


def test_bhv8_body_too_large_413():
    """F-3/ADR-4: corps > MAX_BODY → 413, rien enregistré, aucun HMAC calculé."""
    client, store = _make_client()
    oversized = b"x" * (MAX_BODY + 1)
    # Signature délibérément invalide — on ne doit jamais l'atteindre
    headers = {"X-Timestamp": str(NOW), "X-Signature": "sha256=aabbccdd"}
    resp = client.post("/webhooks/acme", content=oversized, headers=headers)
    assert resp.status_code == 413
    assert store.get("any-id") is None


# --- Source inconnue → 401 (même réponse que signature invalide, INV-6) ---


def test_unknown_source_401():
    client, store = _make_client()
    raw = _raw(event_id="evt-z", type="test", data={})
    headers = {"X-Timestamp": str(NOW), "X-Signature": "sha256=abc123"}
    resp = client.post("/webhooks/unknown-source", content=raw, headers=headers)
    assert resp.status_code == 401
    assert store.get("evt-z") is None
