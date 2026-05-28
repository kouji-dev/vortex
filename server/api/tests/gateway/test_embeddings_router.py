"""Multi-provider embedding routing — model → provider, batch, dimensions.

Pure unit tests for :class:`EmbeddingRouter` and its prefix resolver. No
HTTP layer here; the compat-surface tests live in
``compat/test_openai_embeddings_routing.py``.
"""

from __future__ import annotations

import pytest

from ai_portal.gateway.embeddings import (
    EmbeddingRouter,
    default_provider_for_model,
)
from ai_portal.gateway.types import Embeddings, Usage


class _RecordingProvider:
    """Captures every embed call so tests can assert routing + batching."""

    def __init__(
        self,
        *,
        name: str,
        max_batch: int = 16,
        supports_dimensions: bool = True,
        dim: int = 4,
    ):
        self.name = name
        self.max_batch = max_batch
        self.supports_dimensions = supports_dimensions
        self._dim = dim
        self.calls: list[dict] = []

    async def embed(
        self,
        texts: list[str],
        model: str,
        *,
        dimensions: int | None = None,
    ) -> Embeddings:
        self.calls.append(
            {
                "texts": list(texts),
                "model": model,
                "dimensions": dimensions,
            }
        )
        d = dimensions or self._dim
        vecs = [[float(i + len(t)) for i in range(d)] for t in texts]
        return Embeddings(
            model=model,
            provider=self.name,
            vectors=vecs,
            usage=Usage(input_tokens=len(texts), total_tokens=len(texts)),
        )


# ── default prefix resolver ──────────────────────────────────────────────


def test_default_resolver_picks_openai_for_text_embedding_3() -> None:
    assert default_provider_for_model("text-embedding-3-small") == "openai"
    assert default_provider_for_model("text-embedding-3-large") == "openai"


def test_default_resolver_picks_voyage_for_voyage_models() -> None:
    assert default_provider_for_model("voyage-3") == "voyage"
    assert default_provider_for_model("voyage-large-2") == "voyage"


def test_default_resolver_picks_cohere_for_embed_english() -> None:
    assert default_provider_for_model("embed-english-v3") == "cohere"


def test_default_resolver_raises_for_unknown_model() -> None:
    with pytest.raises(KeyError):
        default_provider_for_model("totally-made-up-model")


# ── router.embed: multi-provider routing ─────────────────────────────────


@pytest.mark.asyncio
async def test_routes_openai_model_to_openai_provider() -> None:
    openai = _RecordingProvider(name="openai")
    voyage = _RecordingProvider(name="voyage")
    router = EmbeddingRouter()
    router.register(openai)
    router.register(voyage)

    emb = await router.embed(["hi"], "text-embedding-3-small")

    assert emb.provider == "openai"
    assert len(openai.calls) == 1
    assert voyage.calls == []
    assert openai.calls[0]["model"] == "text-embedding-3-small"


@pytest.mark.asyncio
async def test_routes_voyage_model_to_voyage_provider() -> None:
    openai = _RecordingProvider(name="openai")
    voyage = _RecordingProvider(name="voyage")
    router = EmbeddingRouter()
    router.register(openai)
    router.register(voyage)

    emb = await router.embed(["hi"], "voyage-3")

    assert emb.provider == "voyage"
    assert len(voyage.calls) == 1
    assert openai.calls == []


@pytest.mark.asyncio
async def test_unknown_model_raises_keyerror() -> None:
    router = EmbeddingRouter()
    with pytest.raises(KeyError):
        await router.embed(["hi"], "made-up-model")


# ── batching: 100 inputs respects max_batch ──────────────────────────────


@pytest.mark.asyncio
async def test_batch_split_respects_provider_max_batch() -> None:
    openai = _RecordingProvider(name="openai", max_batch=16)
    router = EmbeddingRouter()
    router.register(openai)

    inputs = [f"text-{i}" for i in range(100)]
    emb = await router.embed(inputs, "text-embedding-3-small")

    # 100 / 16 → 7 batches (sizes 16,16,16,16,16,16,4).
    assert len(openai.calls) == 7
    sizes = [len(c["texts"]) for c in openai.calls]
    assert sizes == [16, 16, 16, 16, 16, 16, 4]
    # Vectors reassembled in input order, count matches input.
    assert len(emb.vectors) == 100
    # Usage summed across batches.
    assert emb.usage.input_tokens == 100


@pytest.mark.asyncio
async def test_batch_preserves_input_order_across_chunks() -> None:
    openai = _RecordingProvider(name="openai", max_batch=3, dim=2)
    router = EmbeddingRouter()
    router.register(openai)

    inputs = [f"len-{n}" for n in (1, 22, 333, 4444, 55555)]
    emb = await router.embed(inputs, "text-embedding-3-small")
    # Provider yields vectors based on text length; we round-trip those
    # to ensure ordering is preserved across the 3+2 split.
    assert len(emb.vectors) == 5
    lengths_in_vectors = [int(v[1]) for v in emb.vectors]
    expected = [(1 + len(t)) for t in inputs]  # second slot is i=1 + len(t)
    assert lengths_in_vectors == expected


# ── dimensions passthrough ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dimensions_forwarded_to_supporting_provider() -> None:
    openai = _RecordingProvider(name="openai", supports_dimensions=True)
    router = EmbeddingRouter()
    router.register(openai)

    emb = await router.embed(
        ["hi"], "text-embedding-3-small", dimensions=512
    )
    assert openai.calls[0]["dimensions"] == 512
    # Provider returned 512-dim vector.
    assert len(emb.vectors[0]) == 512


@pytest.mark.asyncio
async def test_dimensions_ignored_when_provider_does_not_support() -> None:
    voyage = _RecordingProvider(name="voyage", supports_dimensions=False)
    router = EmbeddingRouter()
    router.register(voyage)

    await router.embed(["hi"], "voyage-3", dimensions=512)
    # Provider call received dimensions=None even though caller asked 512.
    assert voyage.calls[0]["dimensions"] is None
