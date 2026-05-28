"""KB playground service — exercised against a fake Session.

The session only needs ``add``/``commit``/``refresh``: the service never
queries via the session inside ``run`` (it only writes a row). That lets us
verify behaviour without spinning up a real DB.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone

import pytest

from ai_portal.rag.playground.schemas import (
    PlaygroundRequest,
    PlaygroundSettings,
    RetrievedChunk,
)
from ai_portal.rag.playground.service import KbPlaygroundService


class _FakeRow:
    def __init__(self, **kwargs) -> None:
        self.id = _uuid.uuid4()
        self.created_at = datetime.now(timezone.utc)
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeSession:
    def __init__(self) -> None:
        self.added: list = []

    def add(self, row) -> None:
        # mimic ORM defaults for the row
        row.id = _uuid.uuid4()
        row.created_at = datetime.now(timezone.utc)
        self.added.append(row)

    def commit(self) -> None:
        pass

    def refresh(self, row) -> None:
        pass


@pytest.mark.asyncio
async def test_playground_run_returns_retrieved_chunks() -> None:
    async def fake_retrieve(kb_id: int, query: str, settings: PlaygroundSettings):
        assert kb_id == 7
        assert query == "what is rag"
        assert settings.top_k == 3
        return [
            RetrievedChunk(
                chunk_id="c1", document_id="d1", text="lorem", score=0.9
            ),
            RetrievedChunk(
                chunk_id="c2", document_id="d2", text="ipsum", score=0.5
            ),
        ]

    db = _FakeSession()
    svc = KbPlaygroundService(db=db, retrieve=fake_retrieve)
    req = PlaygroundRequest(
        query="what is rag",
        settings=PlaygroundSettings(top_k=3),
        save=True,
    )

    resp = await svc.run(kb_id=7, user_id=42, req=req)

    assert resp.query == "what is rag"
    assert len(resp.retrieved) == 2
    assert resp.retrieved[0].chunk_id == "c1"
    assert resp.answer == ""
    assert resp.session_id is not None
    # session was persisted
    assert len(db.added) == 1


@pytest.mark.asyncio
async def test_playground_run_with_answer_callable() -> None:
    async def fake_retrieve(kb_id, query, settings):
        return [
            RetrievedChunk(chunk_id="c1", document_id="d1", text="t", score=0.5)
        ]

    async def fake_answer(query, chunks, settings):
        assert query == "Q"
        assert len(chunks) == 1
        return "the answer", [{"n": 1, "document_id": "d1"}]

    db = _FakeSession()
    svc = KbPlaygroundService(db=db, retrieve=fake_retrieve, answer=fake_answer)
    resp = await svc.run(
        kb_id=1,
        user_id=None,
        req=PlaygroundRequest(query="Q", save=False),
    )

    assert resp.answer == "the answer"
    assert resp.citations == [{"n": 1, "document_id": "d1"}]
    # save=False → no row persisted
    assert resp.session_id is None
    assert db.added == []


@pytest.mark.asyncio
async def test_playground_run_save_false_does_not_persist() -> None:
    async def fake_retrieve(kb_id, query, settings):
        return []

    db = _FakeSession()
    svc = KbPlaygroundService(db=db, retrieve=fake_retrieve)
    resp = await svc.run(
        kb_id=1,
        user_id=None,
        req=PlaygroundRequest(query="x", save=False),
    )

    assert resp.session_id is None
    assert db.added == []
