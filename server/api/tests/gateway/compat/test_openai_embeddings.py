"""B2: OpenAI-compatible /v1/embeddings tests.

Verify request shape → :class:`Embeddings` translation, response shape →
OpenAI ``list`` envelope with ``data[].embedding`` floats. The provider's
``embed`` method is stubbed via a fake provider.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_portal.gateway.compat.openai_embeddings import router as embeddings_router
from ai_portal.gateway.service import get_llm_provider
from ai_portal.gateway.types import (
    Capability,
    Embeddings,
    Usage,
)


class _RecordingEmbedProvider:
    name = "fake-embed"
    capabilities: set[Capability] = {"embeddings"}

    def __init__(
        self,
        *,
        vectors: list[list[float]] | None = None,
        provider_name: str | None = None,
    ):
        self._vectors = vectors or [[0.1, 0.2, 0.3]]
        self._provider_name = provider_name or "openai"
        self.last_texts: list[str] | None = None
        self.last_model: str | None = None

    async def embed(self, texts: list[str], model: str) -> Embeddings:
        self.last_texts = list(texts)
        self.last_model = model
        # Mirror the input count if caller passed more than one text.
        vecs = self._vectors
        if len(texts) > len(vecs):
            vecs = [vecs[0] for _ in texts]
        return Embeddings(
            model=model,
            provider=self._provider_name,
            vectors=vecs[: len(texts)],
            usage=Usage(input_tokens=sum(len(t) // 4 + 1 for t in texts), total_tokens=0),
        )

    async def complete_canonical(self, req):  # pragma: no cover
        raise NotImplementedError

    async def stream_canonical(self, req):  # pragma: no cover
        raise NotImplementedError
        yield  # noqa: PLE0101

    def count_tokens(self, text, model):  # pragma: no cover
        return 1

    async def list_models(self):  # pragma: no cover
        return []

    async def health(self):  # pragma: no cover
        from ai_portal.gateway.types import HealthStatus
        return HealthStatus(healthy=True)


def _build_app(provider) -> FastAPI:
    app = FastAPI()
    app.include_router(embeddings_router)
    app.dependency_overrides[get_llm_provider] = lambda: provider
    return app


# ── single-input ────────────────────────────────────────────────────────


def test_embeddings_single_string_input():
    provider = _RecordingEmbedProvider(vectors=[[0.1, 0.2, 0.3, 0.4]])
    client = TestClient(_build_app(provider))

    res = client.post(
        "/v1/embeddings",
        json={"model": "text-embedding-3-small", "input": "hello world"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["object"] == "list"
    assert body["model"] == "text-embedding-3-small"
    assert len(body["data"]) == 1
    item = body["data"][0]
    assert item["object"] == "embedding"
    assert item["index"] == 0
    assert item["embedding"] == [0.1, 0.2, 0.3, 0.4]
    # All embedding values are floats.
    assert all(isinstance(x, float) for x in item["embedding"])
    # Usage block present.
    assert "usage" in body
    assert "prompt_tokens" in body["usage"]
    assert "total_tokens" in body["usage"]

    # Provider received the right call.
    assert provider.last_texts == ["hello world"]
    assert provider.last_model == "text-embedding-3-small"


def test_embeddings_list_input():
    provider = _RecordingEmbedProvider(vectors=[[0.0, 0.0], [1.0, 1.0]])
    client = TestClient(_build_app(provider))

    res = client.post(
        "/v1/embeddings",
        json={
            "model": "text-embedding-3-small",
            "input": ["one", "two"],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["data"]) == 2
    assert body["data"][0]["index"] == 0
    assert body["data"][1]["index"] == 1
    assert body["data"][0]["embedding"] == [0.0, 0.0]
    assert body["data"][1]["embedding"] == [1.0, 1.0]


def test_embeddings_rejects_empty_input():
    provider = _RecordingEmbedProvider()
    client = TestClient(_build_app(provider))

    res = client.post(
        "/v1/embeddings",
        json={"model": "text-embedding-3-small", "input": []},
    )
    assert res.status_code == 422


def test_embeddings_honors_request_id_header():
    provider = _RecordingEmbedProvider()
    client = TestClient(_build_app(provider))

    res = client.post(
        "/v1/embeddings",
        headers={"x-request-id": "req-emb-1"},
        json={"model": "text-embedding-3-small", "input": "hi"},
    )
    assert res.status_code == 200
    assert res.headers.get("x-request-id") == "req-emb-1"


def test_embeddings_provider_without_embed_returns_501():
    """A provider that raises NotImplementedError surfaces as 501."""

    class _NoEmbed:
        name = "noop"
        capabilities: set[Capability] = set()

        async def embed(self, texts, model):
            raise NotImplementedError("no embeddings here")

        async def complete_canonical(self, req):  # pragma: no cover
            raise NotImplementedError

        async def stream_canonical(self, req):  # pragma: no cover
            raise NotImplementedError
            yield  # noqa: PLE0101

        def count_tokens(self, text, model):  # pragma: no cover
            return 1

        async def list_models(self):  # pragma: no cover
            return []

        async def health(self):  # pragma: no cover
            from ai_portal.gateway.types import HealthStatus
            return HealthStatus(healthy=True)

    client = TestClient(_build_app(_NoEmbed()))
    res = client.post(
        "/v1/embeddings",
        json={"model": "text-embedding-3-small", "input": "hi"},
    )
    assert res.status_code == 501


def test_embeddings_encoding_format_base64():
    """When ``encoding_format=base64`` requested, returned embeddings are b64-encoded floats."""
    import base64
    import struct

    provider = _RecordingEmbedProvider(vectors=[[0.5, -0.25]])
    client = TestClient(_build_app(provider))

    res = client.post(
        "/v1/embeddings",
        json={
            "model": "text-embedding-3-small",
            "input": "hi",
            "encoding_format": "base64",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    enc = body["data"][0]["embedding"]
    # Must be a string when base64.
    assert isinstance(enc, str)
    decoded = base64.b64decode(enc)
    # 2 floats × 4 bytes = 8 bytes.
    assert len(decoded) == 8
    floats = list(struct.unpack(f"{len(decoded)//4}f", decoded))
    assert abs(floats[0] - 0.5) < 1e-6
    assert abs(floats[1] - -0.25) < 1e-6
