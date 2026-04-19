"""Quota enforcement — check_quota returns block when limit exceeded."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from tests.conftest import requires_postgres


@requires_postgres
def test_quota_allows_when_no_quota_row():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.usage.service import check_quota

    db = SessionLocal()
    try:
        decision = check_quota(
            db,
            org_id=uuid.uuid4(),
            user_id=9999,
            api_model_id="gpt-4o",
        )
        assert decision.action == "allow"
        assert not decision.is_blocked
    finally:
        db.close()


@requires_postgres
def test_quota_blocks_when_cost_exceeded():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.usage.service import check_quota, record_usage
    from ai_portal.usage.model import UsageQuota

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        user_id = 42

        # Set quota at $0.001 — very low so one usage record exceeds it.
        with bypass_rls(db):
            quota = UsageQuota(
                org_id=org_id,
                user_id=user_id,
                api_model_id=None,
                period="day",
                max_cost_usd=Decimal("0.000001"),
                action_on_breach="block",
            )
            db.add(quota)
            db.commit()

        # Record usage that exceeds the cap.
        record_usage(
            db,
            org_id=org_id,
            user_id=user_id,
            conversation_id=None,
            message_id=None,
            api_model_id="claude-3-5-sonnet-20241022",
            usage={"input_tokens": 10000, "output_tokens": 5000},
        )

        decision = check_quota(db, org_id=org_id, user_id=user_id, api_model_id="claude-3-5-sonnet-20241022")
        assert decision.is_blocked
        assert decision.action == "block"
        assert decision.retry_after_seconds is not None and decision.retry_after_seconds > 0

    finally:
        db.close()


@requires_postgres
def test_quota_warn_action():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.usage.service import check_quota, record_usage
    from ai_portal.usage.model import UsageQuota

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        user_id = 43

        with bypass_rls(db):
            quota = UsageQuota(
                org_id=org_id,
                user_id=user_id,
                period="day",
                max_cost_usd=Decimal("0.000001"),
                action_on_breach="warn",
            )
            db.add(quota)
            db.commit()

        record_usage(
            db,
            org_id=org_id,
            user_id=user_id,
            conversation_id=None,
            message_id=None,
            api_model_id="gpt-4o",
            usage={"input_tokens": 100000, "output_tokens": 50000},
        )

        decision = check_quota(db, org_id=org_id, user_id=user_id, api_model_id="gpt-4o")
        assert decision.action == "warn"
        assert not decision.is_blocked

    finally:
        db.close()
