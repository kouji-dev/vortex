"""RLS isolation tests — confirm cross-org data is invisible."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

from tests.conftest import requires_postgres


@requires_postgres
def test_rls_set_org_context_hides_other_org_rows():
    """set_org_context switches role and sets app.org_id so RLS filters apply."""
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import set_org_context, bypass_rls
    from ai_portal.audit.model import AuditEvent

    db = SessionLocal()
    try:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()

        # Insert rows for both orgs bypassing RLS.
        with bypass_rls(db):
            ev_a = AuditEvent(
                org_id=org_a,
                actor_type="user",
                event_type="test.a",
                resource_type="test",
                action="create",
            )
            ev_b = AuditEvent(
                org_id=org_b,
                actor_type="user",
                event_type="test.b",
                resource_type="test",
                action="create",
            )
            db.add_all([ev_a, ev_b])
            db.commit()

        # Scope to org A — should see only org_a row.
        set_org_context(db, org_a)
        rows_a = db.query(AuditEvent).filter(
            AuditEvent.event_type.in_(["test.a", "test.b"])
        ).all()
        assert len(rows_a) == 1
        assert rows_a[0].org_id == org_a

        # Scope to org B — should see only org_b row.
        set_org_context(db, org_b)
        rows_b = db.query(AuditEvent).filter(
            AuditEvent.event_type.in_(["test.a", "test.b"])
        ).all()
        assert len(rows_b) == 1
        assert rows_b[0].org_id == org_b

        # No context — should see nothing.
        set_org_context(db, None)
        rows_none = db.query(AuditEvent).filter(
            AuditEvent.event_type.in_(["test.a", "test.b"])
        ).all()
        assert len(rows_none) == 0

    finally:
        db.close()


@requires_postgres
def test_bypass_rls_sees_all_orgs():
    """bypass_rls context manager lets workers read across org boundaries."""
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.audit.model import AuditEvent

    db = SessionLocal()
    try:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()

        with bypass_rls(db):
            ev_a = AuditEvent(org_id=org_a, actor_type="system", event_type="bypass.a", resource_type="test", action="create")
            ev_b = AuditEvent(org_id=org_b, actor_type="system", event_type="bypass.b", resource_type="test", action="create")
            db.add_all([ev_a, ev_b])
            db.commit()

        with bypass_rls(db):
            all_rows = db.query(AuditEvent).filter(
                AuditEvent.event_type.in_(["bypass.a", "bypass.b"])
            ).all()
        assert len(all_rows) == 2

    finally:
        db.close()
