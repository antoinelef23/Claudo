import hmac as _hmac
from unittest.mock import patch


from gateway.model import MAX_SKEW
from gateway.verify import sign, verify

NOW = 1_700_000_000
SECRET = b"test-secret"
BODY = b'{"event_id":"e1","type":"pay","data":{}}'


def _sig(ts: int = NOW, body: bytes = BODY, secret: bytes = SECRET) -> str:
    return sign(secret, ts, body)


def test_sign_returns_hex():
    result = sign(SECRET, NOW, BODY)
    assert isinstance(result, str)
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


def test_verify_valid():
    assert verify(SECRET, NOW, BODY, _sig(), NOW) is True


def test_verify_valid_with_sha256_prefix():
    assert verify(SECRET, NOW, BODY, "sha256=" + _sig(), NOW) is True


def test_verify_mutated_signature_byte():
    sig = _sig()
    mutated = ("0" if sig[0] != "0" else "1") + sig[1:]
    assert verify(SECRET, NOW, BODY, mutated, NOW) is False


def test_verify_mutated_body_byte():
    bad_body = BODY[:-1] + (b"X" if BODY[-1:] != b"X" else b"Y")
    assert verify(SECRET, NOW, bad_body, _sig(), NOW) is False


def test_verify_skew_exactly_max_positive():
    assert verify(SECRET, NOW, BODY, _sig(), NOW + MAX_SKEW) is True


def test_verify_skew_exactly_max_negative():
    assert verify(SECRET, NOW, BODY, _sig(), NOW - MAX_SKEW) is True


def test_verify_skew_one_over_max_positive():
    assert verify(SECRET, NOW, BODY, _sig(), NOW + MAX_SKEW + 1) is False


def test_verify_skew_one_over_max_negative():
    assert verify(SECRET, NOW, BODY, _sig(), NOW - MAX_SKEW - 1) is False


def test_verify_uses_compare_digest():
    with patch.object(_hmac, "compare_digest", wraps=_hmac.compare_digest) as mock_cd:
        result = verify(SECRET, NOW, BODY, _sig(), NOW)
    assert result is True
    assert mock_cd.called
