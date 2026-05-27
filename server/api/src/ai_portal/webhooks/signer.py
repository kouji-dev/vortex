"""HMAC-SHA256 webhook signing.

Wire format: ``v1=<hex>`` (lowercase hex digest, no whitespace).
Header convention: ``X-Webhook-Signature: v1=<hex>``.
"""

from __future__ import annotations

import hashlib
import hmac

SIG_PREFIX = "v1="


def sign_payload(payload: bytes, secret: bytes) -> str:
    """Return ``v1=<hex>`` HMAC-SHA256 of ``payload`` with ``secret``."""
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes")
    if not isinstance(secret, (bytes, bytearray)):
        raise TypeError("secret must be bytes")
    digest = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return SIG_PREFIX + digest


def verify_signature(payload: bytes, secret: bytes, signature: str) -> bool:
    """Constant-time signature check.

    Returns False on prefix mismatch / malformed signature / digest mismatch.
    """
    if not signature or not signature.startswith(SIG_PREFIX):
        return False
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, signature)
