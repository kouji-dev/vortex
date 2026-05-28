"""Tiny hashing + excerpt utilities for audit payloads.

Centralized so every hook hashes identically — the chain in
``ai_portal.audit.chain`` then re-hashes the audit row itself.
"""

from __future__ import annotations

import hashlib


def sha256_hex(data: bytes | str) -> str:
    """SHA-256 of ``data``. Strings encoded as UTF-8."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def excerpt(text: str, *, head: int = 200, tail: int = 100) -> str:
    """Return a short, truncated excerpt safe to store in audit JSON.

    ``head`` chars from the start, ``…`` marker, ``tail`` chars from the end.
    Total length is clamped — no full stdout dumps end up in audit rows.
    """
    if not text:
        return ""
    if len(text) <= head + tail + 1:
        return text
    return f"{text[:head]}…{text[-tail:]}"
