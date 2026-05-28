"""Read-side helpers — transparent decrypt of usage-event ciphertext columns."""

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
        logger.warning("usage decrypt failed: %s", exc)
        return None


def pricing_snapshot(event: Any) -> dict | list | None:
    enc = getattr(event, "pricing_snapshot_enc", None)
    if enc is not None:
        out = _safe_decrypt(enc)
        if out is not None:
            return out
    return getattr(event, "pricing_snapshot", None)


def meta(event: Any) -> dict | list | None:
    enc = getattr(event, "meta_enc", None)
    if enc is not None:
        out = _safe_decrypt(enc)
        if out is not None:
            return out
    return getattr(event, "meta", None)
