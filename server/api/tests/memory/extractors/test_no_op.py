"""Phase C1 — no_op extractor."""
from __future__ import annotations

import pytest

from ai_portal.memory.extractors import get
from ai_portal.memory.extractors.no_op import NoOpExtractor
from ai_portal.memory.extractors.protocol import ExtractOpts, ExtractScope, Turn


@pytest.mark.asyncio
async def test_no_op_returns_empty() -> None:
    e = NoOpExtractor()
    scope = ExtractScope(
        org_id="00000000-0000-0000-0000-000000000001",
        actor_user_id="1",
        scope_kind="user",
        scope_id="1",
    )
    out = await e.extract(
        [Turn(role="user", content="anything at all", turn_id="t1")],
        scope,
        ExtractOpts(),
    )
    assert out == []


def test_no_op_registered() -> None:
    assert get("no_op").name == "no_op"
