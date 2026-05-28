"""Phase C2 — rule_based extractor."""
from __future__ import annotations

import pytest

from ai_portal.memory.extractors import get
from ai_portal.memory.extractors.protocol import ExtractOpts, ExtractScope, Turn
from ai_portal.memory.extractors.rule_based import RuleBasedExtractor


@pytest.fixture
def scope() -> ExtractScope:
    return ExtractScope(
        org_id="00000000-0000-0000-0000-000000000001",
        actor_user_id="1",
        scope_kind="user",
        scope_id="1",
    )


@pytest.mark.asyncio
async def test_preference_match(scope) -> None:
    e = RuleBasedExtractor()
    cands = await e.extract(
        [Turn(role="user", content="I prefer dark mode.", turn_id="t1")],
        scope,
        ExtractOpts(),
    )
    assert len(cands) == 1
    assert cands[0].type == "preference"
    assert "dark mode" in cands[0].text


@pytest.mark.asyncio
async def test_entity_workplace(scope) -> None:
    e = RuleBasedExtractor()
    cands = await e.extract(
        [Turn(role="user", content="I work at Acme Corp.", turn_id="t2")],
        scope,
        ExtractOpts(),
    )
    assert any(c.type == "entity" and "Acme" in c.text for c in cands)


@pytest.mark.asyncio
async def test_no_match(scope) -> None:
    e = RuleBasedExtractor()
    cands = await e.extract(
        [Turn(role="user", content="The weather is nice today.", turn_id="t3")],
        scope,
        ExtractOpts(),
    )
    assert cands == []


@pytest.mark.asyncio
async def test_ignores_assistant_role(scope) -> None:
    e = RuleBasedExtractor()
    cands = await e.extract(
        [Turn(role="assistant", content="I prefer your approach.", turn_id="ta")],
        scope,
        ExtractOpts(),
    )
    assert cands == []


@pytest.mark.asyncio
async def test_confidence_floor_drops_low(scope) -> None:
    e = RuleBasedExtractor()
    cands = await e.extract(
        [Turn(role="user", content="I like coffee.", turn_id="t4")],
        scope,
        ExtractOpts(confidence_floor=0.95),
    )
    assert cands == []


def test_rule_based_registered() -> None:
    assert get("rule_based").name == "rule_based"
