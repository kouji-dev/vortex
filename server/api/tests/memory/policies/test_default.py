"""Phase F1 — default policy."""
from __future__ import annotations

import pytest

from ai_portal.memory.extractors.protocol import ExtractScope, Turn
from ai_portal.memory.policies import get
from ai_portal.memory.policies.default import DefaultPolicy
from ai_portal.memory.recallers.protocol import RecallScope


@pytest.mark.asyncio
async def test_default_should_extract_always_true() -> None:
    pol = DefaultPolicy()
    scope = ExtractScope(
        org_id="00000000-0000-0000-0000-000000000001",
        actor_user_id="1",
        scope_kind="user",
        scope_id="1",
    )
    assert await pol.should_extract(Turn(role="user", content="x", turn_id="t1"), scope) is True


@pytest.mark.asyncio
async def test_default_should_recall_always_true() -> None:
    pol = DefaultPolicy()
    scope = RecallScope(org_id="x", actor_user_id="1")
    assert await pol.should_recall("any query", scope) is True


@pytest.mark.asyncio
async def test_default_no_sensitive_match() -> None:
    pol = DefaultPolicy()
    assert await pol.sensitive_category_match("I am diagnosed with diabetes") == []


def test_registered() -> None:
    assert get("default").name == "default"
