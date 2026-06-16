import hashlib
import hmac

from gateway.model import MAX_SKEW


def sign(secret: bytes, timestamp: int, raw_body: bytes) -> str:
    """HMAC-SHA256 hex over `{timestamp}.{raw_body}` (ADR-2)."""
    msg = f"{timestamp}.".encode() + raw_body
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def verify(
    secret: bytes,
    timestamp: int,
    raw_body: bytes,
    signature: str,
    now: int,
) -> bool:
    """True iff signature is valid (constant-time) AND |now - timestamp| <= MAX_SKEW.

    Accepts optional sha256= prefix on the signature header (ADR-2).
    Never logs secret, signature, or payload (INV-6). Returns only bool (INV-1, INV-6).
    """
    if signature.startswith("sha256="):
        signature = signature[7:]
    expected = sign(secret, timestamp, raw_body)
    if not hmac.compare_digest(expected, signature):  # INV-2: constant-time
        return False
    return abs(now - timestamp) <= MAX_SKEW
