"""``POST /v1/embeddings`` honours the registered :class:`EmbeddingRouter`.

Locks down the wire contract:

- Model id picks the provider via the router's resolver.
- Batch dispatch is observable via per-provider call counts.
- ``dimensions`` flag forwards to providers that support it.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_portal.gateway.compat.openai_embeddings import (
    get_embedding_router,
    router as embeddings_router,
)
from ai_portal.gateway.embeddings import EmbeddingRouter
from ai_portal.gateway.service import get_llm_provider
from ai_portal.gateway.types import Capability, Embeddings, Usage


class _Provider:
    def __init__(self, *, name: str, max_batch: int = 8, supports_dim: bool = True):
        self.name = name
        self.max_batch = max_batch
        self.supports_dimensions = supports_dim
        self.calls: list[dict] = []

    async def embed(
        self, texts, model, *, dimensions=None
    ) -> Embeddings:  # noqa: ANN001
        self.calls.append(
            {"texts": list(texts), "model": model, "dimensions": dimensions}
        )
        dim = dimensions or 3
        return Embeddings(
            model=model,
            provider=self.name,
            vectors=[[0.0] * dim for _ in texts],
            usage=Usage(input_tokens=len(texts), total_tokens=len(texts)),
        )


def _stub_llm_provider():
    """Required dep — but unused when an EmbeddingRouter is registered."""

    class _Unused:
        name = "unused"
        capabilities: set[Capability] = set()

        async def embed(self, *_a, **_k):  # pragma: no cover
            raise NotImplementedError

        async def complete_canonical(self, req):  # pragma: no cover
            raise NotImplementedError

        async def stream_canonical(self, req):  # pragma: no cover
            raise NotImplementedError
            yield  # noqa: PLE0101

    return _Unused()


def _build_app(router: EmbeddingRouter) -> FastAPI:
    app = FastAPI()
    app.include_router(embeddings_router)
    app.dependency_overrides[get_llm_provider] = _stub_llm_provider
    app.dependency_overrides[get_embedding_router] = lambda: router
    return app


def test_routes_text_embedding_to_openai_provider() -> None:
    openai = _Provider(name="openai")
    voyage = _Provider(name="voyage")
    er = EmbeddingRouter()
    er.register(openai)
    er.register(voyage)
    client = TestClient(_build_app(er))

    res = client.post(
        "/v1/embeddings",
        json={"model": "text-embedding-3-small", "input": "hello"},
    )
    assert res.status_code == 200, res.text
    assert len(openai.calls) == 1
    assert voyage.calls == []


def test_routes_voyage_model_to_voyage_provider() -> None:
    openai = _Provider(name="openai")
    voyage = _Provider(name="voyage")
    er = EmbeddingRouter()
    er.register(openai)
    er.register(voyage)
    client = TestClient(_build_app(er))

    res = client.post(
        "/v1/embeddings",
        json={"model": "voyage-3", "input": "hello"},
    )
    assert res.status_code == 200, res.text
    assert len(voyage.calls) == 1
    assert openai.calls == []


def test_100_inputs_split_into_batches_respecting_max() -> None:
    openai = _Provider(name="openai", max_batch=20)
    er = EmbeddingRouter()
    er.register(openai)
    client = TestClient(_build_app(er))

    inputs = [f"t{i}" for i in range(100)]
    res = client.post(
        "/v1/embeddings",
        json={"model": "text-embedding-3-small", "input": inputs},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["data"]) == 100
    # 100 / 20 = 5 batches.
    assert len(openai.calls) == 5
    sizes = [len(c["texts"]) for c in openai.calls]
    assert sizes == [20, 20, 20, 20, 20]


def test_dimensions_param_forwarded_to_openai() -> None:
    openai = _Provider(name="openai", supports_dim=True)
    er = EmbeddingRouter()
    er.register(openai)
    client = TestClient(_build_app(er))

    res = client.post(
        "/v1/embeddings",
        json={
            "model": "text-embedding-3-small",
            "input": "hi",
            "dimensions": 512,
        },
    )
    assert res.status_code == 200, res.text
    assert openai.calls[0]["dimensions"] == 512
    # Returned vector reflects the requested dimension.
    body = res.json()
    assert len(body["data"][0]["embedding"]) == 512


def test_dimensions_dropped_for_non_supporting_provider() -> None:
    voyage = _Provider(name="voyage", supports_dim=False)
    er = EmbeddingRouter()
    er.register(voyage)
    client = TestClient(_build_app(er))

    res = client.post(
        "/v1/embeddings",
        json={"model": "voyage-3", "input": "hi", "dimensions": 512},
    )
    assert res.status_code == 200, res.text
    assert voyage.calls[0]["dimensions"] is None


def test_unknown_model_returns_400() -> None:
    er = EmbeddingRouter()
    er.register(_Provider(name="openai"))
    client = TestClient(_build_app(er))

    res = client.post(
        "/v1/embeddings",
        json={"model": "totally-unknown-model", "input": "hi"},
    )
    assert res.status_code == 400
