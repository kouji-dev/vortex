"""B6: POST /v1/rerank — Cohere-shaped wire format.

Provider selection is delegated by overriding ``get_reranker`` in the
FastAPI app dep so we don't hit the network.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_portal.gateway.rerank import RerankResult


class _StubReranker:
    """Returns the docs in reverse with descending fake scores."""

    name = "stub"
    last_call: dict | None = None

    async def rerank(
        self,
        *,
        query: str,
        documents: list[str],
        top_k: int | None = None,
        model: str | None = None,
        return_documents: bool = False,
    ) -> list[RerankResult]:
        _StubReranker.last_call = {
            "query": query,
            "documents": list(documents),
            "top_k": top_k,
            "model": model,
            "return_documents": return_documents,
        }
        n = len(documents)
        out = [
            RerankResult(
                index=i,
                relevance_score=float(n - i) / n,
                document=documents[i] if return_documents else None,
            )
            for i in range(n)
        ]
        if top_k is not None:
            out = out[:top_k]
        return out


def _build_app(*, actor, reranker) -> FastAPI:
    from ai_portal.control_plane.deps import require_actor
    from ai_portal.gateway.compat.rerank import get_reranker, router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_actor] = lambda: actor
    app.dependency_overrides[get_reranker] = lambda: reranker
    return app


@pytest.fixture(autouse=True)
def _reset_stub():
    _StubReranker.last_call = None
    yield


def test_rerank_returns_sorted_results_cohere_shape():
    from ai_portal.rbac.service import Actor

    actor = Actor(org_id=uuid.uuid4(), kind="user", user_id=1)
    client = TestClient(_build_app(actor=actor, reranker=_StubReranker()))

    res = client.post(
        "/v1/rerank",
        json={
            "query": "what is RAG?",
            "documents": ["a", "b", "c"],
            "model": "rerank-2",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    # Cohere top-level keys: id, results, meta.
    assert "id" in body
    assert "results" in body
    # Sorted descending by score.
    scores = [r["relevance_score"] for r in body["results"]]
    assert scores == sorted(scores, reverse=True)
    # Indices map back to originals.
    assert {r["index"] for r in body["results"]} == {0, 1, 2}


def test_rerank_top_n_truncates_in_response():
    from ai_portal.rbac.service import Actor

    actor = Actor(org_id=uuid.uuid4(), kind="user", user_id=1)
    client = TestClient(_build_app(actor=actor, reranker=_StubReranker()))

    res = client.post(
        "/v1/rerank",
        json={
            "query": "q",
            "documents": ["a", "b", "c", "d", "e"],
            "top_n": 2,
        },
    )
    assert res.status_code == 200
    assert len(res.json()["results"]) == 2
    # Stub captured top_k from the route handler.
    assert _StubReranker.last_call["top_k"] == 2


def test_rerank_return_documents_includes_doc_text():
    from ai_portal.rbac.service import Actor

    actor = Actor(org_id=uuid.uuid4(), kind="user", user_id=1)
    client = TestClient(_build_app(actor=actor, reranker=_StubReranker()))
    res = client.post(
        "/v1/rerank",
        json={
            "query": "q",
            "documents": ["alpha", "beta"],
            "return_documents": True,
        },
    )
    assert res.status_code == 200
    body = res.json()
    docs = [r["document"]["text"] for r in body["results"]]
    assert set(docs) == {"alpha", "beta"}


def test_rerank_rejects_empty_documents():
    from ai_portal.rbac.service import Actor

    actor = Actor(org_id=uuid.uuid4(), kind="user", user_id=1)
    client = TestClient(_build_app(actor=actor, reranker=_StubReranker()))
    res = client.post(
        "/v1/rerank",
        json={"query": "q", "documents": []},
    )
    assert res.status_code == 422
