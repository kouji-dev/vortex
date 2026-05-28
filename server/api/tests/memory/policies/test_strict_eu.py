"""Phase F2 — strict_eu policy (GDPR Article 9)."""
from __future__ import annotations

import pytest

from ai_portal.memory.extractors.protocol import ExtractScope, Turn
from ai_portal.memory.policies import get
from ai_portal.memory.policies.strict_eu import StrictEuPolicy
from ai_portal.memory.recallers.protocol import RecallScope


@pytest.fixture
def pol() -> StrictEuPolicy:
    return StrictEuPolicy()


@pytest.fixture
def escope() -> ExtractScope:
    return ExtractScope(
        org_id="00000000-0000-0000-0000-000000000001",
        actor_user_id="1",
        scope_kind="user",
        scope_id="1",
    )


@pytest.mark.asyncio
async def test_blocks_health(pol) -> None:
    matches = await pol.sensitive_category_match("I am diagnosed with diabetes.")
    assert "health" in matches


@pytest.mark.asyncio
async def test_blocks_religion(pol) -> None:
    assert "religious_or_philosophical_beliefs" in await pol.sensitive_category_match(
        "I am a devout Christian."
    )


@pytest.mark.asyncio
async def test_blocks_political(pol) -> None:
    assert "political_opinions" in await pol.sensitive_category_match(
        "I voted Labour last year."
    )


@pytest.mark.asyncio
async def test_blocks_sexual_orientation(pol) -> None:
    assert "sex_life_or_sexual_orientation" in await pol.sensitive_category_match(
        "My sexual orientation is private."
    )


@pytest.mark.asyncio
async def test_blocks_biometric(pol) -> None:
    assert "biometric" in await pol.sensitive_category_match(
        "I scanned my fingerprint."
    )


@pytest.mark.asyncio
async def test_clean_text_returns_empty(pol) -> None:
    assert await pol.sensitive_category_match("I prefer TypeScript.") == []


@pytest.mark.asyncio
async def test_should_extract_blocks_when_sensitive(pol, escope) -> None:
    out = await pol.should_extract(
        Turn(role="user", content="I have cancer", turn_id="t"),
        escope,
    )
    assert out is False


@pytest.mark.asyncio
async def test_should_extract_allows_clean(pol, escope) -> None:
    out = await pol.should_extract(
        Turn(role="user", content="I prefer dark mode", turn_id="t"),
        escope,
    )
    assert out is True


@pytest.mark.asyncio
async def test_should_recall_blocks_sensitive_query(pol) -> None:
    scope = RecallScope(org_id="x", actor_user_id="1")
    assert await pol.should_recall("what is my diagnosis?", scope) is False


def test_registered() -> None:
    assert get("strict_eu").name == "strict_eu"
