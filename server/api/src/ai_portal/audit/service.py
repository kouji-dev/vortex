"""Audit log service — write path + hash chain + sink fan-out.

Public surface:

- :func:`emit_audit` — high-level helper. Builds the canonical payload,
  computes the Merkle ``hash`` chained off the org's prior event, writes to
  Postgres, then fans out to any extra sinks configured for the org.
- :func:`log_event` — legacy fire-and-forget wrapper retained for callers
  that previously used it. Routes through ``emit_audit`` synchronously when
  Redis is unavailable.

Writes are wrapped in ``bypass_rls`` so the trigger lets the row through.
The DB-level trigger still blocks UPDATE/DELETE outside bypass.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from ai_portal.audit.chain import compute_hash
from ai_portal.audit.model import AuditEvent, AuditRetentionConfig
from ai_portal.audit.protocol import AuditEventPayload
from ai_portal.audit.registry import resolve_sinks_for_org
from ai_portal.core.crypto import encrypt_json

logger = logging.getLogger(__name__)


def emit_audit(
    *,
    org_id: uuid.UUID | str,
    event_type: str,
    actor: dict[str, Any] | None = None,
    resource: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    actor_user_id: int | None = None,
    actor_type: str = "user",
    request_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    action: str | None = None,
) -> AuditEventPayload | None:
    """Append one audit event. Returns the recorded payload (or None on failure).

    - ``actor`` / ``resource`` are shorthand dicts. ``resource`` may include
      ``type`` and ``id``; ``action`` defaults to the part of ``event_type``
      after the last ``.``.
    - Chain: locks on the org and reads the latest stored ``hash`` to use as
      ``prev_hash``. The lock is a no-op for our volume (one row insert per
      audited action) but prevents concurrent inserts from forking the chain.
    """
    org_uuid = org_id if isinstance(org_id, uuid.UUID) else uuid.UUID(str(org_id))
    actor = actor or {}
    resource = resource or {}
    if action is None:
        action = event_type.rsplit(".", 1)[-1] if "." in event_type else event_type

    resource_type = resource.get("type") or resource.get("resource_type") or "unknown"
    resource_id = resource.get("id") or resource.get("resource_id")

    try:
        from ai_portal.core.db.rls import bypass_rls  # noqa: PLC0415
        from ai_portal.core.db.session import SessionLocal  # noqa: PLC0415

        with SessionLocal() as db:  # type: Session
            with bypass_rls(db):
                # Lock the latest event for this org. Postgres advisory lock on a
                # 64-bit derived from the org UUID prevents chain forks.
                lock_key = int.from_bytes(org_uuid.bytes[:8], "big", signed=True)
                db.execute(
                    _text("SELECT pg_advisory_xact_lock(:k)"),
                    {"k": lock_key},
                )
                prev_hash = db.execute(
                    select(AuditEvent.hash)
                    .where(AuditEvent.org_id == org_uuid)
                    .order_by(AuditEvent.id.desc())
                    .limit(1)
                ).scalar_one_or_none()

                created_at = datetime.now(tz=UTC)
                event_id = uuid.uuid4()
                h = compute_hash(
                    event_id=event_id,
                    org_id=org_uuid,
                    event_type=event_type,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    payload=payload,
                    created_at=created_at,
                    prev_hash=prev_hash,
                )

                actor_dict = actor or None
                row = AuditEvent(
                    event_id=event_id,
                    org_id=org_uuid,
                    actor_user_id=actor_user_id,
                    actor_type=actor_type,
                    actor_json=None,
                    actor_enc=encrypt_json(actor_dict),
                    event_type=event_type,
                    resource_type=resource_type,
                    resource_id=str(resource_id) if resource_id is not None else None,
                    action=action,
                    payload_json=None,
                    payload_enc=encrypt_json(payload),
                    metadata_=None,
                    request_id=request_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    prev_hash=prev_hash,
                    hash=h,
                    created_at=created_at,
                )
                db.add(row)
                db.commit()
                db.refresh(row)

        recorded = AuditEventPayload(
            event_id=row.event_id,
            org_id=row.org_id,
            actor_user_id=row.actor_user_id,
            actor_type=row.actor_type,
            actor_json=actor_dict,
            event_type=row.event_type,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            action=row.action,
            payload=payload,
            metadata=payload,
            request_id=row.request_id,
            ip_address=str(row.ip_address) if row.ip_address else None,
            user_agent=row.user_agent,
            prev_hash=row.prev_hash,
            hash=row.hash,
            created_at=row.created_at,
        )

        # Fan out to extra sinks (best-effort; never raise on sink failure).
        _fanout_sinks(org_uuid, recorded)
        return recorded
    except Exception as exc:  # noqa: BLE001
        logger.warning("emit_audit failed: %s", exc)
        return None


def _fanout_sinks(org_id: uuid.UUID, event: AuditEventPayload) -> None:
    """Resolve sinks for the org and write the event to each, best-effort."""
    try:
        from ai_portal.core.db.rls import bypass_rls  # noqa: PLC0415
        from ai_portal.core.db.session import SessionLocal  # noqa: PLC0415

        with SessionLocal() as db:
            with bypass_rls(db):
                cfg = db.execute(
                    select(AuditRetentionConfig).where(AuditRetentionConfig.org_id == org_id)
                ).scalar_one_or_none()
        sink_configs = cfg.sink_configs if cfg else []
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit sink config lookup failed: %s", exc)
        return

    sinks = resolve_sinks_for_org(sink_configs or [])
    if not sinks:
        return

    async def _run_all() -> None:
        for s in sinks:
            try:
                await s.write(event)
            except Exception as exc:  # noqa: BLE001
                logger.warning("audit sink %s.write failed: %s", getattr(s, "name", "?"), exc)

    # Run synchronously from a thread so the caller (possibly sync) is not blocked
    # on the event loop and we don't crash when there is no running loop.
    def _runner() -> None:
        try:
            asyncio.run(_run_all())
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit sink fanout crashed: %s", exc)

    threading.Thread(target=_runner, daemon=True).start()


# --- Back-compat layer ----------------------------------------------------

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
    """Legacy entry point — routes through :func:`emit_audit` synchronously."""
    try:
        from ai_portal.core.config import get_settings  # noqa: PLC0415
        settings = get_settings()
        if not getattr(settings, "audit_enabled", True):
            return
    except Exception:  # noqa: BLE001
        pass

    emit_audit(
        org_id=org_id,
        event_type=event_type,
        actor={"user_id": actor_user_id, "type": actor_type} if actor_user_id is not None else None,
        resource={"type": resource_type, "id": resource_id},
        payload=metadata,
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        request_id=request_id,
        ip_address=ip_address,
        user_agent=user_agent,
        action=action,
    )


def _text(s: str):
    """Lazy ``sqlalchemy.text`` shim to avoid an extra top-level import."""
    from sqlalchemy import text  # noqa: PLC0415
    return text(s)
