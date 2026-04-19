"""Retention sweeper — prunes old conversations; legal hold blocks sweeper."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.conftest import requires_postgres


def _old_ts() -> str:
    """ISO timestamp 100 days ago."""
    return (datetime.now(UTC) - timedelta(days=100)).isoformat()


def _make_slug() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


@requires_postgres
def test_sweeper_deletes_old_conversations():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.chat.model import ChatConversation
    from ai_portal.retention.model import RetentionPolicy
    from ai_portal.retention.sweeper import sweep_org
    from ai_portal.auth.model import User, Org

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()

        with bypass_rls(db):
            # Minimal org row — slug is required.
            org = Org(id=org_id, slug=_make_slug(), name="sweep-test-org")
            db.add(org)
            db.flush()

            rp = RetentionPolicy(
                org_id=org_id,
                conversation_retention_days=30,
                legal_hold=False,
            )
            db.add(rp)

            user = User(email=f"sweep-{uuid.uuid4()}@test.com", org_id=org_id, role="member")
            db.add(user)
            db.flush()

            old_conv = ChatConversation(org_id=org_id, user_id=user.id)
            new_conv = ChatConversation(org_id=org_id, user_id=user.id)
            db.add_all([old_conv, new_conv])
            db.commit()

            # Backdate the old conversation via SQL after insert.
            db.execute(
                text("UPDATE chat_conversations SET created_at = :ts WHERE id = :id"),
                {"ts": _old_ts(), "id": old_conv.id},
            )
            db.commit()

            old_id = old_conv.id
            new_id = new_conv.id

        sweep_org(db, rp)

        with bypass_rls(db):
            still_old = db.get(ChatConversation, old_id)
            still_new = db.get(ChatConversation, new_id)

        assert still_old is None, "Old conversation should have been deleted"
        assert still_new is not None, "Recent conversation should survive"

    finally:
        db.close()


@requires_postgres
def test_sweeper_skips_legal_hold_org():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.chat.model import ChatConversation
    from ai_portal.retention.model import RetentionPolicy
    from ai_portal.retention.sweeper import sweep_all_orgs
    from ai_portal.auth.model import User, Org

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()

        with bypass_rls(db):
            org = Org(id=org_id, slug=_make_slug(), name="legal-hold-org")
            db.add(org)
            db.flush()

            rp = RetentionPolicy(
                org_id=org_id,
                conversation_retention_days=1,
                legal_hold=True,
            )
            db.add(rp)

            user = User(email=f"hold-{uuid.uuid4()}@test.com", org_id=org_id, role="member")
            db.add(user)
            db.flush()

            old_conv = ChatConversation(org_id=org_id, user_id=user.id)
            db.add(old_conv)
            db.commit()

            # Backdate.
            db.execute(
                text("UPDATE chat_conversations SET created_at = :ts WHERE id = :id"),
                {"ts": _old_ts(), "id": old_conv.id},
            )
            db.commit()
            old_id = old_conv.id

        # sweep_all_orgs skips orgs with legal_hold=True.
        sweep_all_orgs(db)

        with bypass_rls(db):
            still_there = db.get(ChatConversation, old_id)

        assert still_there is not None, "Legal-hold org conversations must NOT be deleted"

    finally:
        db.close()
