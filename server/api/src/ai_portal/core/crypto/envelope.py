"""Column-level envelope encryption helpers.

Threat model: protect the JSON payloads in ``audit_events.payload_json`` /
``audit_events.actor_json`` and ``usage_events.meta`` / ``pricing_snapshot``
from disclosure if a Postgres dump leaks.

Design:
- One key-encryption key (KEK) from ``AUDIT_KEK`` env var (urlsafe base64 32
  bytes — Fernet format). Per-row data-encryption keys (DEK) are *not* used
  here; the KEK encrypts the payload directly. This is sufficient for the
  column-level "encryption at rest" requirement and keeps queries possible
  via the dedicated keyed-hash columns rather than searching the ciphertext.
- ``encrypt_json(d)`` returns a base64 token (bytes). ``decrypt_json(tok)``
  reverses it. Both are deterministic in their behaviour around ``None``:
  ``None`` -> ``None``.
- If no KEK is configured the helpers fall back to a stable no-op marker
  prefix ``b"plain:"`` so existing rows remain readable. Production runs
  MUST set ``AUDIT_KEK``.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_KEK_ENV = "AUDIT_KEK"
_PLAIN_PREFIX = b"plain:"


class EnvelopeError(RuntimeError):
    """Raised when a token is malformed or fails authentication."""


@lru_cache(maxsize=1)
def _fernet() -> Fernet | None:
    raw = os.environ.get(_KEK_ENV, "").strip()
    if not raw:
        return None
    try:
        # Fernet expects a 32-byte urlsafe base64-encoded key.
        return Fernet(raw.encode("ascii"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("AUDIT_KEK invalid (%s); falling back to plain marker", exc)
        return None


def reset_cache() -> None:
    """Test hook — wipe the cached Fernet so env changes are observed."""
    _fernet.cache_clear()  # type: ignore[attr-defined]


def encrypt_json(value: dict | list | None) -> bytes | None:
    """Encrypt a JSON-serialisable value to bytes; passthrough on ``None``."""
    if value is None:
        return None
    raw = json.dumps(value, default=str, sort_keys=True).encode("utf-8")
    f = _fernet()
    if f is None:
        return _PLAIN_PREFIX + base64.b64encode(raw)
    return f.encrypt(raw)


def decrypt_json(token: bytes | memoryview | None) -> dict | list | None:
    """Inverse of :func:`encrypt_json`. Returns ``None`` for ``None`` input."""
    if token is None:
        return None
    buf = bytes(token) if isinstance(token, memoryview) else token
    if buf.startswith(_PLAIN_PREFIX):
        try:
            raw = base64.b64decode(buf[len(_PLAIN_PREFIX):])
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise EnvelopeError(f"plain marker decode failed: {exc}") from exc
    f = _fernet()
    if f is None:
        # Token is ciphertext but we have no key — fail loud.
        raise EnvelopeError("ciphertext present but AUDIT_KEK not configured")
    try:
        raw = f.decrypt(buf)
    except InvalidToken as exc:
        raise EnvelopeError("invalid envelope token") from exc
    return json.loads(raw.decode("utf-8"))


def is_configured() -> bool:
    """Return True when a real KEK is loaded (vs the plain-marker fallback)."""
    return _fernet() is not None
