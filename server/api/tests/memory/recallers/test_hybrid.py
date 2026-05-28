"""Phase D3 — hybrid recaller (vector + BM25 + recency + importance)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ai_portal.memory.recallers import get, hybrid
from ai_portal.memory.recallers.hybrid import HybridRecaller
from ai_portal.memory.recallers.protocol import RecallOpts, RecallScope


def _mem(mid: str, text: str, importance: float = 0.5):
    now = datetime.now(tz=timezone.utc)
    return SimpleNamespace(
        id=mid,
        text=text,
        importance=importance,
        last_used_at=None,
        created_at=now - timedelta(days=1),
    )


@pytest.fixture
def scope() -> RecallScope:
    return RecallScope(
        org_id="00000000-0000-0000-0000-000000000001",
        actor_user_id="1",
        team_ids=[],
    )


@pytest.mark.asyncio
async def test_bm25_token_match_boosts_relevant_mem(monkeypatch, scope) -> None:
    r = HybridRecaller(session=None)  # type: ignore[arg-type]

    async def fake_embed(q, s):
        return [0.0] * 1536

    monkeypatch.setattr(r, "_embed", fake_embed)
    rows = [
        # Two candidates with similar vector score; bm25 should pick "the lint command is pnpm lint"
        (_mem("a", "user likes coffee"), 0.30),
        (_mem("b", "the lint command is pnpm lint for repo X"), 0.31),
    ]
    r.repo = SimpleNamespace(vector_search=AsyncMock(return_value=rows))
    out = await r.recall(
        "lint command", scope, RecallOpts(top_k=2, bm25_weight=0.7,
                                          recency_weight=0.0, importance_weight=0.0)
    )
    assert out[0].memory_id == "b"
    assert "bm25" in out[0].explain


@pytest.mark.asyncio
async def test_empty_pool_returns_empty(monkeypatch, scope) -> None:
    r = HybridRecaller(session=None)  # type: ignore[arg-type]

    async def fake_embed(q, s):
        return [0.0] * 1536

    monkeypatch.setattr(r, "_embed", fake_embed)
    r.repo = SimpleNamespace(vector_search=AsyncMock(return_value=[]))
    assert await r.recall("q", scope, RecallOpts()) == []


def test_sentinel_registered() -> None:
    assert get("hybrid").name == "hybrid"


def test_module_has_bm25_flag() -> None:
    assert hasattr(hybrid, "BM25_AVAILABLE")
