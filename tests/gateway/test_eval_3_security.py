"""EVAL-3 — property sécurité : INV-1 (authenticité), INV-2 (comparaison constante), INV-3 (anti-rejeu).

T6 · parallel_group D (disjoint de T4/T5).
Trois volets — (a) SIGNATURE, (b) FENÊTRE, (c) COMPARAISON — tous @pytest.mark.eval.
"""

import inspect
import json
import random
import re

import pytest
from fastapi.testclient import TestClient

from gateway.app import create_app
from gateway.model import MAX_SKEW
from gateway.store import InMemoryStore
from gateway.verify import sign
from gateway.verify import verify as _verify_fn

SECRET = b"acme-test-key"
SECRETS = {"acme": SECRET}
NOW = 1_700_000_000

# Échantillon fixe de corps de requêtes valides utilisés dans les volets (a) et (b).
_SAMPLE: list[tuple[str, str, dict]] = [
    ("sec-s1", "payment", {"amount": 100}),
    ("sec-s2", "order", {"ref": "A", "qty": 3}),
    ("sec-s3", "refund", {"amount": 50, "reason": "return"}),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client() -> tuple[TestClient, InMemoryStore]:
    store = InMemoryStore()
    app = create_app(secrets=SECRETS, store=store, now=lambda: NOW)
    return TestClient(app), store


def _raw(**fields: object) -> bytes:
    return json.dumps(fields).encode()


def _valid_headers(raw: bytes, timestamp: int = NOW) -> dict[str, str]:
    sig = sign(SECRET, timestamp, raw)
    return {"X-Timestamp": str(timestamp), "X-Signature": f"sha256={sig}"}


def _mutate_hex(hex_str: str, pos: int) -> str:
    """Return a copy of `hex_str` with the hex char at `pos` changed to a different char."""
    chars = list(hex_str)
    orig = chars[pos]
    chars[pos] = next(c for c in "0123456789abcdef" if c != orig)
    return "".join(chars)


def _mutate_byte(data: bytes, pos: int) -> bytes:
    """Return a copy of `data` with the byte at `pos` incremented modulo 256."""
    buf = bytearray(data)
    buf[pos] = (buf[pos] + 1) % 256
    return bytes(buf)


# ---------------------------------------------------------------------------
# Volet (a) — SIGNATURE : toute mutation d'un octet → 401, magasin inchangé (INV-1)
# ---------------------------------------------------------------------------


@pytest.mark.eval
def test_eval_3_signature_mutated_sig_header_rejected():
    """Mutation d'un octet de la valeur sha256= → 401, store inchangé (INV-1).

    Testé sur l'échantillon entier ; les positions de mutation sont choisies
    par random.Random(seed=42) pour la reproductibilité.
    """
    rng = random.Random(42)
    for event_id, etype, data in _SAMPLE:
        client, store = _client()
        raw = _raw(event_id=event_id, type=etype, data=data)
        headers = _valid_headers(raw)
        hex_part = headers["X-Signature"][7:]  # retire "sha256="
        pos = rng.randrange(len(hex_part))
        mutated = f"sha256={_mutate_hex(hex_part, pos)}"
        resp = client.post(
            "/webhooks/acme",
            content=raw,
            headers={**headers, "X-Signature": mutated},
        )
        assert resp.status_code == 401, (
            f"[{event_id}] signature mutée au pos {pos} devrait → 401"
        )
        assert store.get(event_id) is None, (
            f"[{event_id}] magasin doit rester vide après signature mutée"
        )


@pytest.mark.eval
def test_eval_3_signature_mutated_body_rejected():
    """Mutation d'un octet du corps (signature inchangée) → 401, store inchangé (INV-1).

    Le corps est inclus dans le message signé (ADR-2 : `{ts}.{raw_body}`), donc
    tout écart corps/signature invalide la vérification.
    """
    rng = random.Random(42)
    for event_id, etype, data in _SAMPLE:
        client, store = _client()
        raw = _raw(event_id=event_id, type=etype, data=data)
        headers = _valid_headers(raw)  # signature calculée sur `raw` original
        pos = rng.randrange(len(raw))
        mutated_raw = _mutate_byte(raw, pos)
        resp = client.post(
            "/webhooks/acme",
            content=mutated_raw,
            headers=headers,  # signature ne correspond plus au corps muté
        )
        assert resp.status_code == 401, (
            f"[{event_id}] corps muté au byte {pos} devrait → 401"
        )
        assert store.get(event_id) is None, (
            f"[{event_id}] magasin doit rester vide après corps muté"
        )


@pytest.mark.eval
def test_eval_3_signature_mutated_timestamp_rejected():
    """Horodatage modifié d'une seconde (signature inchangée) → 401, store inchangé (INV-1).

    L'horodatage est signé dans le message (ADR-2 : `{ts}.{raw_body}`), donc
    envoyer X-Timestamp différent du timestamp signé invalide la signature.
    """
    for event_id, etype, data in _SAMPLE:
        client, store = _client()
        raw = _raw(event_id=event_id, type=etype, data=data)
        original_headers = _valid_headers(raw, timestamp=NOW)
        # Incrémente le timestamp dans l'en-tête — la signature reste calculée sur NOW
        mutated_headers = {**original_headers, "X-Timestamp": str(NOW + 1)}
        resp = client.post("/webhooks/acme", content=raw, headers=mutated_headers)
        assert resp.status_code == 401, (
            f"[{event_id}] timestamp muté (NOW+1, sig sur NOW) devrait → 401"
        )
        assert store.get(event_id) is None, (
            f"[{event_id}] magasin doit rester vide après timestamp muté"
        )


# ---------------------------------------------------------------------------
# Volet (b) — FENÊTRE : la borne est EXACTE (INV-3)
# ---------------------------------------------------------------------------


@pytest.mark.eval
def test_eval_3_window_at_max_skew_past_accepted():
    """timestamp = now - MAX_SKEW (exactement à la borne inférieure) → 202 (INV-3)."""
    client, store = _client()
    ts = NOW - MAX_SKEW
    raw = _raw(event_id="win-past-ok", type="test", data={})
    resp = client.post("/webhooks/acme", content=raw, headers=_valid_headers(raw, ts))
    assert resp.status_code == 202, (
        f"timestamp = now - MAX_SKEW ({ts}) doit être accepté (202)"
    )
    assert store.get("win-past-ok") is not None


@pytest.mark.eval
def test_eval_3_window_at_max_skew_future_accepted():
    """timestamp = now + MAX_SKEW (exactement à la borne supérieure) → 202 (INV-3)."""
    client, store = _client()
    ts = NOW + MAX_SKEW
    raw = _raw(event_id="win-future-ok", type="test", data={})
    resp = client.post("/webhooks/acme", content=raw, headers=_valid_headers(raw, ts))
    assert resp.status_code == 202, (
        f"timestamp = now + MAX_SKEW ({ts}) doit être accepté (202)"
    )
    assert store.get("win-future-ok") is not None


@pytest.mark.eval
def test_eval_3_window_past_max_skew_plus_one_rejected():
    """timestamp = now - (MAX_SKEW + 1) (une seconde au-delà de la borne) → 401 (INV-3)."""
    client, store = _client()
    ts = NOW - (MAX_SKEW + 1)
    raw = _raw(event_id="win-past-ko", type="test", data={})
    resp = client.post("/webhooks/acme", content=raw, headers=_valid_headers(raw, ts))
    assert resp.status_code == 401, (
        f"timestamp = now - (MAX_SKEW+1) ({ts}) doit être rejeté (401)"
    )
    assert store.get("win-past-ko") is None


@pytest.mark.eval
def test_eval_3_window_future_max_skew_plus_one_rejected():
    """timestamp = now + (MAX_SKEW + 1) (une seconde au-delà de la borne) → 401 (INV-3)."""
    client, store = _client()
    ts = NOW + (MAX_SKEW + 1)
    raw = _raw(event_id="win-future-ko", type="test", data={})
    resp = client.post("/webhooks/acme", content=raw, headers=_valid_headers(raw, ts))
    assert resp.status_code == 401, (
        f"timestamp = now + (MAX_SKEW+1) ({ts}) doit être rejeté (401)"
    )
    assert store.get("win-future-ko") is None


# ---------------------------------------------------------------------------
# Volet (c) — COMPARAISON CONSTANTE : hmac.compare_digest, pas == (INV-2)
# ---------------------------------------------------------------------------


@pytest.mark.eval
def test_eval_3_compare_digest_present_in_source():
    """gateway/verify.py doit contenir hmac.compare_digest (INV-2) — vérifié par inspection du source."""
    import gateway.verify as _verify_mod

    source = inspect.getsource(_verify_mod)
    assert "compare_digest" in source, (
        "INV-2 : hmac.compare_digest doit apparaître dans gateway/verify.py"
    )


@pytest.mark.eval
def test_eval_3_no_direct_equality_on_signature_in_source():
    """gateway/verify.py ne doit pas comparer la signature via == (INV-2) — vérifié par inspection du source."""
    import gateway.verify as _verify_mod

    source = inspect.getsource(_verify_mod)
    # Cherche un == entre les deux variables candidats (expected / signature)
    forbidden = re.search(
        r"\b(?:expected|signature)\s*==\s*(?:expected|signature)\b",
        source,
    )
    assert forbidden is None, (
        f"INV-2 violation : comparaison directe `==` sur la signature détectée dans verify.py : "
        f"{forbidden.group() if forbidden else ''}"
    )


@pytest.mark.eval
def test_eval_3_compare_digest_self_test():
    """Auto-test du helper verify() : signature correcte → True, mutée → False (INV-2 comportemental)."""
    raw = _raw(event_id="cd-self", type="test", data={"probe": True})
    correct_sig = sign(SECRET, NOW, raw)

    # Signature correcte (avec préfixe sha256=) → True
    assert _verify_fn(SECRET, NOW, raw, f"sha256={correct_sig}", NOW) is True

    # Mutation de chaque nibble : toujours False
    rng = random.Random(42)
    for _ in range(8):
        pos = rng.randrange(len(correct_sig))
        mutated = _mutate_hex(correct_sig, pos)
        assert _verify_fn(SECRET, NOW, raw, f"sha256={mutated}", NOW) is False, (
            f"verify() doit renvoyer False pour la signature mutée au pos {pos}"
        )
