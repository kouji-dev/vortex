"""Postgres audit sink — primary store, queryable.

This is the default sink. The write path here is a no-op because the
service layer always commits to Postgres first (so the hash chain can read
back the previous event's hash). ``query`` is the real surface.
"""

from __future__ import annotations

from sqlalchemy import select

from ai_portal.audit.event_view import decrypt_actor as _decrypt_actor
from ai_portal.audit.event_view import decrypt_payload as _decrypt_payload
from ai_portal.audit.model import AuditEvent
from ai_portal.audit.protocol import AuditEventPayload, AuditFilter
from ai_portal.core.db.rls import bypass_rls


class PostgresAuditSink:
    name = "postgres"

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def write(self, event: AuditEventPayload) -> None:
        # No-op: the service already writes to Postgres before fanning out.
        return None

    async def query(self, f: AuditFilter) -> list[AuditEventPayload]:
        with self._session_factory() as db:  # type: Session
            with bypass_rls(db):
                q = select(AuditEvent)
                if f.org_id is not None:
                    q = q.where(AuditEvent.org_id == f.org_id)
                if f.actor_user_id is not None:
                    q = q.where(AuditEvent.actor_user_id == f.actor_user_id)
                if f.event_type:
                    q = q.where(AuditEvent.event_type == f.event_type)
                if f.resource_type:
                    q = q.where(AuditEvent.resource_type == f.resource_type)
                if f.resource_id:
                    q = q.where(AuditEvent.resource_id == f.resource_id)
                if f.action:
                    q = q.where(AuditEvent.action == f.action)
                if f.start:
                    q = q.where(AuditEvent.created_at >= f.start)
                if f.end:
                    q = q.where(AuditEvent.created_at < f.end)
                q = q.order_by(AuditEvent.created_at.asc()).limit(f.limit).offset(f.offset)
                rows = db.scalars(q).all()

        return [
            AuditEventPayload(
                event_id=r.event_id,
                org_id=r.org_id,
                actor_user_id=r.actor_user_id,
                actor_type=r.actor_type,
                actor_json=_decrypt_actor(r),
                event_type=r.event_type,
                resource_type=r.resource_type,
                resource_id=r.resource_id,
                action=r.action,
                payload=_decrypt_payload(r),
                metadata=_decrypt_payload(r),
                request_id=r.request_id,
                ip_address=str(r.ip_address) if r.ip_address else None,
                user_agent=r.user_agent,
                prev_hash=r.prev_hash,
                hash=r.hash,
                created_at=r.created_at,
            )
            for r in rows
        ]
