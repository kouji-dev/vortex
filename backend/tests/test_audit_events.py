"""Audit log — log_event writes rows with correct metadata."""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import requires_postgres


@requires_postgres
def test_log_event_creates_audit_row():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.audit.service import log_event
    from ai_portal.audit.model import AuditEvent

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        log_event(
            org_id=org_id,
            actor_user_id=7,
            event_type="conversation.create",
            resource_type="conversation",
            resource_id="99",
            action="create",
            metadata={"title": "test chat"},
        )

        with bypass_rls(db):
            rows = db.query(AuditEvent).filter(
                AuditEvent.org_id == org_id,
                AuditEvent.event_type == "conversation.create",
            ).all()

        assert len(rows) == 1
        assert rows[0].actor_user_id == 7
        assert rows[0].resource_id == "99"
        assert rows[0].action == "create"
        meta = rows[0].metadata or {}
        assert meta.get("title") == "test chat"

    finally:
        db.close()


@requires_postgres
def test_log_event_system_actor():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.audit.service import log_event
    from ai_portal.audit.model import AuditEvent

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        log_event(
            org_id=org_id,
            actor_user_id=None,
            actor_type="system",
            event_type="retention.sweep",
            resource_type="policy",
            resource_id=None,
            action="delete",
        )

        with bypass_rls(db):
            rows = db.query(AuditEvent).filter(
                AuditEvent.org_id == org_id,
                AuditEvent.event_type == "retention.sweep",
            ).all()

        assert len(rows) == 1
        assert rows[0].actor_user_id is None
        assert rows[0].actor_type == "system"

    finally:
        db.close()
