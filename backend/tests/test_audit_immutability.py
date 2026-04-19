"""Audit immutability — DB trigger blocks UPDATE/DELETE on audit_events."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError, DatabaseError

from tests.conftest import requires_postgres


@requires_postgres
def test_audit_event_update_blocked_by_trigger():
    """Trigger should raise when UPDATE is attempted without bypass."""
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.audit.model import AuditEvent

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()

        # Insert row (permitted — INSERT is allowed).
        with bypass_rls(db):
            ev = AuditEvent(
                org_id=org_id,
                actor_type="user",
                event_type="immutability.test",
                resource_type="test",
                action="create",
            )
            db.add(ev)
            db.commit()
            row_id = ev.id

        # Attempt UPDATE outside bypass — trigger must fire.
        try:
            with bypass_rls(db):
                # Temporarily disable bypass to let trigger fire.
                db.execute(text("SET LOCAL app.bypass_rls = 'off'"))
                db.execute(
                    text("UPDATE audit_events SET action = 'update' WHERE id = :id"),
                    {"id": row_id},
                )
            db.commit()
            pytest.fail("Expected trigger to prevent UPDATE")
        except (IntegrityError, OperationalError, ProgrammingError, DatabaseError):
            db.rollback()
    finally:
        db.close()


@requires_postgres
def test_audit_event_delete_blocked_by_trigger():
    """Trigger should raise when DELETE is attempted without bypass."""
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.audit.model import AuditEvent

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()

        with bypass_rls(db):
            ev = AuditEvent(
                org_id=org_id,
                actor_type="user",
                event_type="immutability.delete.test",
                resource_type="test",
                action="create",
            )
            db.add(ev)
            db.commit()
            row_id = ev.id

        try:
            with bypass_rls(db):
                db.execute(text("SET LOCAL app.bypass_rls = 'off'"))
                db.execute(
                    text("DELETE FROM audit_events WHERE id = :id"),
                    {"id": row_id},
                )
            db.commit()
            pytest.fail("Expected trigger to prevent DELETE")
        except (IntegrityError, OperationalError, ProgrammingError, DatabaseError):
            db.rollback()
    finally:
        db.close()
