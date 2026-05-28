"""Pluggable webhook dispatch stub.

Real implementation lands in ``ai_portal.webhooks.service`` (Phase F). Until
then, this provides a no-op default and a registration hook so callers
(budgets, audit, etc.) can be wired today and have their events delivered
once F3 ships.
"""
from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any, Callable

logger = logging.getLogger(__name__)

EmitterFn = Callable[[str, dict[str, Any], _uuid.UUID], None]

_emitter: EmitterFn | None = None


def register_emitter(fn: EmitterFn) -> None:
    """Phase F3 calls this once to wire the real dispatcher."""
    global _emitter
    _emitter = fn


def emit_webhook(event_type: str, payload: dict[str, Any], org_id: _uuid.UUID) -> None:
    if _emitter is None:
        logger.debug(
            "webhook (stub) event=%s org=%s payload=%s",
            event_type, org_id, payload,
        )
        return
    _emitter(event_type, payload, org_id)
