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
    app = create_app(
        secrets=SECRETS, store=store, now=lambda: NOW, read_token="read-test-token"
    )
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


# ---------------------------------------------------------------------------
# Volet (d) — F-2 : signature non-ASCII / non-hexadécimale → 401, jamais 500 (BHV-2, ADR-4)
# ---------------------------------------------------------------------------


@pytest.mark.eval
def test_eval_3_d_non_ascii_signature_401():
    """Signature contenant des octets non-ASCII → 401, jamais 500 (BHV-2/F-2, ADR-4).

    Sans la garde F-2, compare_digest lèverait TypeError sur ces octets,
    provoquant un 500 qui constituerait un oracle d'erreur (INV-6 violé).
    """
    # ASCII non-hex → envoyables en str. Octets non-ASCII (0x80-0xFF) → envoyés en BYTES car
    # httpx refuse d'encoder un str non-ASCII côté client (Starlette les décode latin-1 côté app,
    # ce qui ferait lever TypeError à compare_digest sans la garde F-2).
    ascii_non_hex = ["sha256=gggg", "sha256=ZZZZ!@#$"]
    non_ascii_bytes = [b"sha256=caf\xe9", b"sha256=\x80\xff\xfe"]
    for sig in ascii_non_hex + non_ascii_bytes:
        client, store = _client()
        raw = _raw(event_id="sec-nonascii", type="test", data={})
        headers = {"X-Timestamp": str(NOW), "X-Signature": sig}
        resp = client.post("/webhooks/acme", content=raw, headers=headers)
        assert resp.status_code == 401, (
            f"Signature non-hex/non-ASCII {sig!r} doit → 401 (pas 500)"
        )
        assert store.get("sec-nonascii") is None


# ---------------------------------------------------------------------------
# Volet (e) — F-1 / INV-7 : GET /events/{id} sans X-Read-Token valide → 401 (ADR-4)
# ---------------------------------------------------------------------------


@pytest.mark.eval
def test_eval_3_e_get_without_read_token_401():
    """GET /events/{id} sans X-Read-Token → 401, aucun payload (INV-7/F-1, IDOR fermé).

    Vérifie : token absent → 401, token invalide → 401, token valide → 200.
    """
    client, store = _client()
    # Injecter un événement connu
    raw = _raw(event_id="sec-idor", type="test", data={"secret": "confidential"})
    sig = f"sha256={sign(SECRET, NOW, raw)}"
    r = client.post(
        "/webhooks/acme",
        content=raw,
        headers={"X-Timestamp": str(NOW), "X-Signature": sig},
    )
    assert r.status_code == 202

    # Token absent → 401
    resp_no_token = client.get("/events/sec-idor")
    assert resp_no_token.status_code == 401, "Token absent doit → 401"

    # Token invalide → 401
    resp_bad_token = client.get("/events/sec-idor", headers={"X-Read-Token": "wrong"})
    assert resp_bad_token.status_code == 401, "Token invalide doit → 401"

    # Token valide → 200 (santé)
    resp_ok = client.get(
        "/events/sec-idor", headers={"X-Read-Token": "read-test-token"}
    )
    assert resp_ok.status_code == 200, "Token valide doit → 200"
    assert resp_ok.json()["event_id"] == "sec-idor"


# ---------------------------------------------------------------------------
# Volet (f) — F-3 / BHV-8 : corps > MAX_BODY → 413 avant tout HMAC (ADR-4)
# ---------------------------------------------------------------------------


@pytest.mark.eval
def test_eval_3_f_body_too_large_413():
    """Corps > MAX_BODY → 413 avant lecture intégrale / calcul HMAC (BHV-8/F-3, ADR-4).

    Le corps surdimensionné porte une signature intentionnellement invalide pour
    prouver que le 413 est émis avant tout calcul HMAC.
    """
    from gateway.app import MAX_BODY

    client, store = _client()
    oversized = b"x" * (MAX_BODY + 1)
    headers = {
        "X-Timestamp": str(NOW),
        "X-Signature": "sha256=aabbccdd",  # invalide — ne doit jamais être évalué
    }
    resp = client.post("/webhooks/acme", content=oversized, headers=headers)
    assert resp.status_code == 413, (
        f"Corps de {len(oversized)} octets (> MAX_BODY={MAX_BODY}) doit → 413"
    )
    assert store.get("any") is None, "Aucun événement ne doit être enregistré"
