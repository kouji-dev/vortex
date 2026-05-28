"""Read-side helpers — transparent decrypt of audit-event ciphertext columns.

Centralising this here keeps every read path consistent and means the API,
exports and integrity routes all behave the same when ``payload_enc`` /
``actor_enc`` are populated.
"""

from __future__ import annotations

import logging
from typing import Any

from ai_portal.core.crypto import EnvelopeError, decrypt_json

logger = logging.getLogger(__name__)


def _safe_decrypt(blob: Any) -> Any:
    if blob is None:
        return None
    try:
        return decrypt_json(bytes(blob) if not isinstance(blob, bytes) else blob)
    except EnvelopeError as exc:
        logger.warning("audit decrypt failed: %s", exc)
        return None


def decrypt_payload(event: Any) -> dict | list | None:
    """Return the cleartext payload for an audit row, prefer the ciphertext."""
    enc = getattr(event, "payload_enc", None)
    if enc is not None:
        out = _safe_decrypt(enc)
        if out is not None:
            return out
    return getattr(event, "payload_json", None) or getattr(event, "metadata_", None)


def decrypt_actor(event: Any) -> dict | list | None:
    enc = getattr(event, "actor_enc", None)
    if enc is not None:
        out = _safe_decrypt(enc)
        if out is not None:
            return out
    return getattr(event, "actor_json", None)


def decrypt_metadata(event: Any) -> dict | list | None:
    """Back-compat alias used by the router."""
    return decrypt_payload(event)
