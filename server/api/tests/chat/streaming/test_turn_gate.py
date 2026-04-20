# tests/chat/streaming/test_turn_gate.py
import pytest
from fastapi import HTTPException
from unittest.mock import patch

from ai_portal.chat.streaming.turn_gate import evaluate, GateResult


async def test_passes_with_no_policy(async_db_session, org_fixture, user_fixture):
    result = await evaluate(
        session=async_db_session, org_id=org_fixture.id, user_id=user_fixture.id,
        requested_model="gpt-4", requested_tools=["web_search"], requested_capabilities=[],
    )
    assert isinstance(result, GateResult)
    assert result.effective_model == "gpt-4"
    assert "web_search" in result.allowed_tools


async def test_raises_429_on_quota_exceeded(async_db_session, org_fixture, user_fixture):
    """Test that a blocked quota decision raises 429.

    We mock check_quota because the message_usage table does not exist yet
    (it is created in Phase 8 migration). The quota logic itself is tested in
    unit tests for usage.service.
    """
    from ai_portal.usage.service import QuotaDecision

    blocked_decision = QuotaDecision(action="block", reason="Cost quota exceeded")

    with patch("ai_portal.chat.streaming.turn_gate.check_quota", return_value=blocked_decision):
        with pytest.raises(HTTPException) as exc:
            await evaluate(
                session=async_db_session, org_id=org_fixture.id, user_id=user_fixture.id,
                requested_model="gpt-4", requested_tools=[], requested_capabilities=[],
            )
        assert exc.value.status_code == 429
