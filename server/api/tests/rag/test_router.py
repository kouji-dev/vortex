"""HTTP-level smoke tests for the RAG router.

We bypass auth + database by overriding the FastAPI dependencies. The goal
here is to verify that:
  - routes are registered under the expected paths.
  - request bodies are validated.
  - the SSE answer stream serialises events.
  - /api/search dispatches via the provider registry.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch


@pytest.fixture
def client(monkeypatch):
    """Build a minimal FastAPI app that only mounts the rag router.

    Avoids importing the full ai_portal.main (which has unrelated wiring
    issues that are out of scope for this change set).
    """
    from fastapi import FastAPI

    from ai_portal.auth.deps import get_current_org_id, get_current_user, get_db
    from ai_portal.rag.router import router as rag_router
    from ai_portal.knowledge_base import service as kb_svc

    monkeypatch.setattr(kb_svc, "get_owned_kb", lambda db, user, kb_id: MagicMock(id=kb_id))

    app = FastAPI()
    app.include_router(rag_router)

    fake_user = MagicMock(id=42)
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_current_org_id] = lambda: uuid.uuid4()
    app.dependency_overrides[get_db] = lambda: MagicMock()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_search_endpoint_returns_hits(client):
    from ai_portal.rag.search.types import SearchHit

    hits = [
        SearchHit(chunk_id="c1", document_id="d1", kb_id=1, text="abc", score=0.5, meta={"title": "T"}),
    ]
    with patch("ai_portal.rag.router.hybrid_search", return_value=hits):
        r = client.post("/api/kbs/1/search", json={"query": "hi"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["hits"][0]["chunk_id"] == "c1"


def test_search_validates_body(client):
    r = client.post("/api/kbs/1/search", json={})
    assert r.status_code == 422


def test_provider_search_dispatches(client):
    fake_provider = MagicMock()
    from ai_portal.rag.search_providers.protocol import SearchProviderResult

    fake_provider.search.return_value = [
        SearchProviderResult(title="A", url="https://a", snippet="s")
    ]
    with patch("ai_portal.rag.router.get_provider", return_value=fake_provider):
        r = client.post(
            "/api/search", json={"provider": "tavily", "query": "q", "num_results": 1}
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "tavily"
    assert body["results"][0]["title"] == "A"


def test_provider_search_unknown_provider(client):
    r = client.post("/api/search", json={"provider": "nope", "query": "q"})
    assert r.status_code == 404


def test_answer_endpoint_streams_sse(client):
    from ai_portal.rag.answer.service import AnswerEvent, AnswerResult
    from ai_portal.rag.answer.citations import Citation

    def fake_stream(db, req):
        yield AnswerEvent(
            kind="citation",
            citation=Citation(index=1, chunk_id="c1", document_id="d1", kb_id=1, title="T", snippet="s"),
        )
        yield AnswerEvent(kind="delta", text="hello ")
        yield AnswerEvent(kind="delta", text="world [1]")
        yield AnswerEvent(
            kind="final",
            result=AnswerResult(
                text="hello world [1]",
                citations=[Citation(index=1, chunk_id="c1", document_id="d1", kb_id=1, title="T", snippet="s")],
                refused=False,
                used_indices=[1],
                rewritten_query="q",
            ),
        )

    with patch("ai_portal.rag.router.answer_stream", side_effect=fake_stream):
        r = client.post("/api/kbs/1/answer", json={"query": "q"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    raw = r.text
    assert "event: citation" in raw
    assert "event: delta" in raw
    assert "event: final" in raw
    assert "event: done" in raw


def test_federated_answer_requires_kb_ids(client):
    r = client.post("/api/kbs/federated/answer", json={"query": "q", "kb_ids": []})
    assert r.status_code == 422
