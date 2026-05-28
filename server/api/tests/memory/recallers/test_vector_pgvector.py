"""Phase D1 — vector_pgvector recaller (unit-level, mocked repo + embed)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ai_portal.memory.recallers import get, vector_pgvector
from ai_portal.memory.recallers.protocol import RecallOpts, RecallScope
from ai_portal.memory.recallers.vector_pgvector import VectorPgvectorRecaller


def _mem(mid: str, text: str, importance: float, last_used_days_ago: float | None = None):
    now = datetime.now(tz=timezone.utc)
    return SimpleNamespace(
        id=mid,
        text=text,
        importance=importance,
        last_used_at=(
            now - timedelta(days=last_used_days_ago)
            if last_used_days_ago is not None
            else None
        ),
        created_at=now - timedelta(days=2),
    )


@pytest.fixture
def scope() -> RecallScope:
    return RecallScope(
        org_id="00000000-0000-0000-0000-000000000001",
        actor_user_id="1",
        team_ids=[],
    )


@pytest.mark.asyncio
async def test_recall_orders_by_combined_score(monkeypatch, scope) -> None:
    r = VectorPgvectorRecaller(session=None)  # type: ignore[arg-type]

    async def fake_embed(q, scope):
        return [0.1] * 1536

    monkeypatch.setattr(r, "_embed", fake_embed)
    rows = [
        # (memory, distance) — lower distance = better vector match
        (_mem("a", "alpha", importance=0.1), 0.4),
        (_mem("b", "beta", importance=0.9), 0.6),
        (_mem("c", "gamma", importance=0.5), 0.5),
    ]
    r.repo = SimpleNamespace(vector_search=AsyncMock(return_value=rows))
    out = await r.recall(
        "anything",
        scope,
        RecallOpts(top_k=3, recency_weight=0.0, importance_weight=0.0),
    )
    # When recency+importance weights are 0, ordering matches pure vector
    # score (1 - dist) -> a (0.6) > c (0.5) > b (0.4).
    assert [x.memory_id for x in out] == ["a", "c", "b"]
    assert all("vector" in x.explain for x in out)


@pytest.mark.asyncio
async def test_recall_high_importance_weight(monkeypatch, scope) -> None:
    r = VectorPgvectorRecaller(session=None)  # type: ignore[arg-type]

    async def fake_embed(q, scope):
        return [0.0] * 1536

    monkeypatch.setattr(r, "_embed", fake_embed)
    rows = [
        (_mem("a", "alpha", importance=0.1), 0.1),  # high vector, low importance
        (_mem("b", "beta", importance=1.0), 0.2),  # mid vector, high importance
    ]
    r.repo = SimpleNamespace(vector_search=AsyncMock(return_value=rows))
    out = await r.recall(
        "q", scope, RecallOpts(top_k=2, recency_weight=0.0, importance_weight=0.9)
    )
    assert out[0].memory_id == "b"


@pytest.mark.asyncio
async def test_empty_embedding_returns_empty(monkeypatch, scope) -> None:
    r = VectorPgvectorRecaller(session=None)  # type: ignore[arg-type]

    async def fake_embed(q, scope):
        return []

    monkeypatch.setattr(r, "_embed", fake_embed)
    r.repo = SimpleNamespace(vector_search=AsyncMock())
    assert await r.recall("q", scope, RecallOpts()) == []


def test_registered_as_sentinel() -> None:
    sent = get("vector_pgvector")
    assert sent.name == "vector_pgvector"
