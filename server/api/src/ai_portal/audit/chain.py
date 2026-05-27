"""Merkle hash chain for audit_events.

Each event's ``hash`` is a SHA-256 over its canonical fields plus the
previous event's ``hash`` (per org). Re-walking the chain detects any
tampering — even a single mutated byte will break every downstream hash.

The DB-level append-only trigger prevents UPDATE/DELETE, so the only
attack surface left is the disk file itself; periodic chain verification
catches that.
"""

from __future__ import annotations

import hashlib
import json
import uuid as _uuid
from datetime import datetime
from typing import Any


def compute_hash(
    *,
    event_id: _uuid.UUID | str,
    org_id: _uuid.UUID | str,
    event_type: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    payload: Any,
    created_at: datetime,
    prev_hash: str | None,
) -> str:
    """Return hex sha256 over canonical event fields + prev_hash."""
    h = hashlib.sha256()
    parts = (
        str(event_id),
        str(org_id),
        event_type,
        action,
        resource_type,
        str(resource_id or ""),
        json.dumps(payload or {}, sort_keys=True, default=str),
        created_at.isoformat(),
        prev_hash or "",
    )
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def verify_chain(events: list[Any]) -> tuple[bool, int | None]:
    """Walk events in order, recompute each hash, compare against stored.

    ``events`` must be ordered by ``created_at`` ascending within one org.

    Returns ``(ok, first_bad_index)``. ``first_bad_index`` is ``None`` when
    the chain is intact.
    """
    prev = None
    for idx, ev in enumerate(events):
        expected = compute_hash(
            event_id=ev.event_id,
            org_id=ev.org_id,
            event_type=ev.event_type,
            action=ev.action,
            resource_type=ev.resource_type,
            resource_id=ev.resource_id,
            payload=ev.payload_json,
            created_at=ev.created_at,
            prev_hash=prev,
        )
        # The stored prev_hash must match the previously computed expected.
        if ev.prev_hash != prev:
            return False, idx
        if ev.hash != expected:
            return False, idx
        prev = ev.hash
    return True, None
