# server/api/tests/chat/conftest.py
"""Fixtures for chat domain tests."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from ai_portal.chat.item_kinds import ItemKind, ItemRole, ItemStatus
from ai_portal.chat.model import Thread, ThreadItem


# ---------------------------------------------------------------------------
# Low-level fixtures — build on sync_engine from root conftest
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def db_session(sync_engine):
    """A function-scoped SQLAlchemy session that rolls back after each test."""
    with sync_engine.begin() as conn:
        # Each test gets a fresh session that's rolled back at the end.
        session = Session(bind=conn)
        try:
            yield session
        finally:
            session.close()
            conn.rollback()


_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000cf1")
_USER_ID = 99901


@pytest.fixture(scope="function")
def org_fixture(db_session):
    """Insert a test org row; return a simple namespace with .id."""
    # Check if already exists
    existing = db_session.execute(
        text("SELECT id FROM orgs WHERE id = :id"), {"id": str(_ORG_ID)}
    ).first()
    if not existing:
        db_session.execute(
            text("INSERT INTO orgs (id, slug, name) VALUES (:id, 'cf-test-org', 'CF Test Org')"),
            {"id": str(_ORG_ID)},
        )
        db_session.flush()

    class _Org:
        id = _ORG_ID

    return _Org()


@pytest.fixture(scope="function")
def user_fixture(db_session, org_fixture):
    """Insert a test user row; return a simple namespace with .id."""
    existing = db_session.execute(
        text("SELECT id FROM users WHERE id = :id"), {"id": _USER_ID}
    ).first()
    if not existing:
        db_session.execute(
            text(
                "INSERT INTO users (id, email, uuid, org_id) "
                "VALUES (:uid, 'cftest@example.com', gen_random_uuid(), :oid)"
            ),
            {"uid": _USER_ID, "oid": str(org_fixture.id)},
        )
        db_session.flush()

    class _User:
        id = _USER_ID

    return _User()


@pytest.fixture(scope="function")
def thread_with_items(db_session, org_fixture, user_fixture):
    """Create a Thread with 3 ThreadItems; return the Thread."""
    thread = Thread(
        org_id=org_fixture.id,
        user_id=user_fixture.id,
        title="test thread",
        model="gpt-4",
    )
    db_session.add(thread)
    db_session.flush()

    turn = uuid.uuid4()
    items_spec = [
        (ItemKind.user_message, ItemRole.user, {"text": "hi", "attachments": []}),
        (ItemKind.assistant_text, ItemRole.assistant, {"text": "hello"}),
        (ItemKind.turn_end, ItemRole.system, {"reason": "done"}),
    ]
    for kind, role, data in items_spec:
        db_session.add(
            ThreadItem(
                thread_id=thread.id,
                org_id=org_fixture.id,
                turn_id=turn,
                kind=kind,
                role=role,
                status=ItemStatus.done,
                data=data,
            )
        )
    db_session.flush()

    # Detach the thread object before yielding so it's usable in test
    db_session.expire(thread)
    db_session.refresh(thread)
    return thread
