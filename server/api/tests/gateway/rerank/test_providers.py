"""Rerank providers — Voyage / Cohere / BGE.

Each test mocks the underlying HTTP call (or SDK client) and asserts the
provider:

- returns :class:`RerankResult` sorted by descending ``relevance_score``
- honors ``top_k`` truncation
- echoes documents when ``return_documents=True``
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from ai_portal.gateway.rerank import RerankResult


# ── Voyage ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_voyage_rerank_returns_sorted_results():
    """Voyage SDK is mocked to return scores; provider sorts + maps to indices."""
    from ai_portal.gateway.rerank.providers.voyage import VoyageReranker

    class _FakeResult:
        def __init__(self, results):
            self.results = results

    class _FakeRR:
        def __init__(self, index: int, relevance_score: float, document=None):
            self.index = index
            self.relevance_score = relevance_score
            self.document = document

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def rerank(self, query, documents, model, top_k=None):
            # Return in random order — provider must sort.
            return _FakeResult(
                results=[
                    _FakeRR(index=2, relevance_score=0.3),
                    _FakeRR(index=0, relevance_score=0.9),
                    _FakeRR(index=1, relevance_score=0.5),
                ]
            )

    rr = VoyageReranker(api_key="vk_x", client_factory=lambda key: _FakeClient(key))
    out = await rr.rerank(
        query="cats",
        documents=["a", "b", "c"],
        model="rerank-2",
    )
    assert [r.index for r in out] == [0, 1, 2]
    assert out[0].relevance_score == 0.9
    assert all(isinstance(r, RerankResult) for r in out)


@pytest.mark.asyncio
async def test_voyage_rerank_top_k_truncates():
    from ai_portal.gateway.rerank.providers.voyage import VoyageReranker

    class _FakeRR:
        def __init__(self, index, score):
            self.index = index
            self.relevance_score = score
            self.document = None

    class _FakeResult:
        results = [
            _FakeRR(0, 0.9),
            _FakeRR(1, 0.5),
            _FakeRR(2, 0.3),
        ]

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def rerank(self, **kwargs):
            return _FakeResult()

    rr = VoyageReranker(api_key="k", client_factory=lambda k: _FakeClient())
    out = await rr.rerank(query="q", documents=["a", "b", "c"], top_k=2)
    assert len(out) == 2
    assert out[0].relevance_score == 0.9


@pytest.mark.asyncio
async def test_voyage_rerank_returns_documents_when_requested():
    from ai_portal.gateway.rerank.providers.voyage import VoyageReranker

    class _FakeRR:
        def __init__(self, index, score):
            self.index = index
            self.relevance_score = score
            self.document = None

    class _FakeResult:
        results = [_FakeRR(1, 0.8), _FakeRR(0, 0.2)]

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def rerank(self, **kwargs):
            return _FakeResult()

    rr = VoyageReranker(api_key="k", client_factory=lambda k: _FakeClient())
    out = await rr.rerank(
        query="q", documents=["doc-a", "doc-b"], return_documents=True
    )
    assert out[0].document == "doc-b"
    assert out[1].document == "doc-a"


# ── Cohere ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cohere_rerank_calls_cohere_api_and_sorts():
    """Cohere is HTTP-based; intercept with respx + return canned payload."""
    from ai_portal.gateway.rerank.providers.cohere import CohereReranker

    payload = {
        "results": [
            {"index": 1, "relevance_score": 0.2},
            {"index": 0, "relevance_score": 0.95},
        ]
    }
    with respx.mock(base_url="https://api.cohere.com") as mock:
        route = mock.post("/v1/rerank").mock(
            return_value=Response(200, json=payload)
        )
        rr = CohereReranker(api_key="co_x")
        out = await rr.rerank(query="cats", documents=["d0", "d1"], top_k=2)
        assert route.called
        assert [r.index for r in out] == [0, 1]
        # Request body sanity.
        sent = route.calls[0].request
        assert sent.headers["authorization"] == "Bearer co_x"


@pytest.mark.asyncio
async def test_cohere_rerank_top_k_in_request():
    from ai_portal.gateway.rerank.providers.cohere import CohereReranker

    import json as _json

    with respx.mock(base_url="https://api.cohere.com") as mock:
        route = mock.post("/v1/rerank").mock(
            return_value=Response(
                200, json={"results": [{"index": 0, "relevance_score": 1.0}]}
            )
        )
        rr = CohereReranker(api_key="x")
        await rr.rerank(
            query="q", documents=["a", "b", "c"], top_k=1, model="rerank-3"
        )
        body = _json.loads(route.calls[0].request.content.decode())
        assert body["top_n"] == 1
        assert body["model"] == "rerank-3"
        assert body["documents"] == ["a", "b", "c"]


# ── BGE (self-hosted) ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bge_rerank_calls_self_hosted_endpoint():
    """BGE reranker runs behind an HTTP endpoint (e.g. text-embeddings-inference,
    Infinity, or a custom triton service). Provider POSTs ``{query, texts}``
    and reads ``[{index, score}, ...]``.
    """
    from ai_portal.gateway.rerank.providers.bge import BgeReranker

    with respx.mock(base_url="http://bge.local") as mock:
        route = mock.post("/rerank").mock(
            return_value=Response(
                200,
                json=[
                    {"index": 0, "score": 0.1},
                    {"index": 1, "score": 0.9},
                ],
            )
        )
        rr = BgeReranker(base_url="http://bge.local")
        out = await rr.rerank(
            query="x", documents=["a", "b"], model="bge-reranker-large"
        )
        assert route.called
        # Sorted desc by score.
        assert out[0].index == 1
        assert out[0].relevance_score == 0.9


@pytest.mark.asyncio
async def test_bge_returns_documents_when_requested():
    from ai_portal.gateway.rerank.providers.bge import BgeReranker

    with respx.mock(base_url="http://bge.local") as mock:
        mock.post("/rerank").mock(
            return_value=Response(
                200,
                json=[
                    {"index": 1, "score": 0.7},
                    {"index": 0, "score": 0.4},
                ],
            )
        )
        rr = BgeReranker(base_url="http://bge.local")
        out = await rr.rerank(
            query="x", documents=["foo", "bar"], return_documents=True
        )
        assert out[0].document == "bar"
        assert out[1].document == "foo"
