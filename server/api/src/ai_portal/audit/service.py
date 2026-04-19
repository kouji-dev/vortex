"""Audit log service — fire-and-forget write path.

``log_event`` is the only public entry point. It enqueues to Redis RQ when
available, otherwise falls back to a daemon thread. Either way, audit writes
are off the critical path: a metering failure never breaks a chat reply.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def log_event(
    *,
    org_id: uuid.UUID,
    event_type: str,
    resource_type: str,
    action: str,
    actor_user_id: int | None = None,
    actor_type: str = "user",
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Enqueue an audit event asynchronously. Never raises."""
    try:
        from ai_portal.core.config import get_settings  # noqa: PLC0415
        settings = get_settings()
        if not getattr(settings, "audit_enabled", True):
            return

        payload = {
            "org_id": str(org_id),
            "event_type": event_type,
            "resource_type": resource_type,
            "action": action,
            "actor_user_id": actor_user_id,
            "actor_type": actor_type,
            "resource_id": resource_id,
            "metadata": metadata,
            "request_id": request_id,
            "ip_address": ip_address,
            "user_agent": user_agent,
        }

        if settings.redis_url:
            _enqueue_rq(payload, settings.redis_url)
        else:
            _write_in_thread(payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit_log_event_failed: %s", exc)


def _enqueue_rq(payload: dict, redis_url: str) -> None:
    from rq import Queue  # noqa: PLC0415
    from redis import Redis  # noqa: PLC0415
    q = Queue("audit", connection=Redis.from_url(redis_url))
    q.enqueue(_write_audit_event, payload)


def _write_in_thread(payload: dict) -> None:
    threading.Thread(target=_write_audit_event, args=(payload,), daemon=True).start()


def _write_audit_event(payload: dict) -> None:
    """Write one row to audit_events. Called in RQ worker or daemon thread."""
    try:
        from ai_portal.audit.model import AuditEvent  # noqa: PLC0415
        from ai_portal.core.db.session import SessionLocal  # noqa: PLC0415
        from ai_portal.core.db.rls import bypass_rls  # noqa: PLC0415

        with SessionLocal() as db:
            with bypass_rls(db):
                db.add(AuditEvent(
                    org_id=uuid.UUID(payload["org_id"]),
                    event_type=payload["event_type"],
                    resource_type=payload["resource_type"],
                    action=payload["action"],
                    actor_user_id=payload.get("actor_user_id"),
                    actor_type=payload.get("actor_type", "user"),
                    resource_id=payload.get("resource_id"),
                    metadata_=payload.get("metadata"),
                    request_id=payload.get("request_id"),
                    ip_address=payload.get("ip_address"),
                    user_agent=payload.get("user_agent"),
                ))
                db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error("audit_write_failed: %s", exc)
