"""Embeddings routing — model → provider, batch dispatch, dimension passthrough.

The compat surface (``POST /v1/embeddings``) hands the request to
:class:`EmbeddingRouter.embed`. The router:

- Resolves the target provider from the model id (registry of model
  prefixes → provider names + a fallback factory).
- Chunks the input list into batches that respect the provider's
  ``max_batch`` and dispatches them in parallel.
- Reassembles the vectors in input order, preserving the per-batch
  usage totals.
- Threads ``dimensions`` through providers that declare support
  (``"dimensions"`` in their capability spec); silently ignores otherwise.

The router is intentionally simple — it owns no state beyond its
registry. Tests instantiate it directly with fake providers; production
wiring registers concrete provider instances at startup.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from ai_portal.gateway.types import Embeddings, Usage


# ── provider protocol ────────────────────────────────────────────────────


class EmbeddingProvider(Protocol):
    """One provider that exposes ``embed`` over a list of texts.

    Implementations declare:

    - ``name``        — short id (``"openai"``, ``"voyage"`` …)
    - ``max_batch``   — largest batch size accepted in one HTTP call
    - ``supports_dimensions`` — whether the dimension reduction param
      forwards to the provider's body
    """

    name: str
    max_batch: int
    supports_dimensions: bool

    async def embed(
        self,
        texts: list[str],
        model: str,
        *,
        dimensions: int | None = None,
    ) -> Embeddings: ...


# ── registry + router ────────────────────────────────────────────────────


@dataclass
class EmbeddingRouter:
    """Resolve model → provider + run batched embed dispatch.

    ``provider_for_model`` decides which provider handles a model. The
    default uses :func:`default_provider_for_model` (prefix-based map).
    """

    providers: dict[str, EmbeddingProvider] = field(default_factory=dict)
    provider_for_model: Callable[[str], str] | None = None

    def register(self, provider: EmbeddingProvider) -> None:
        """Register a provider by ``provider.name``."""
        self.providers[provider.name] = provider

    async def embed(
        self,
        texts: list[str],
        model: str,
        *,
        dimensions: int | None = None,
    ) -> Embeddings:
        """Route ``(texts, model)`` to the right provider; batch + reassemble."""
        if not texts:
            raise ValueError("texts must not be empty")
        provider_name = self._resolve(model)
        provider = self.providers.get(provider_name)
        if provider is None:
            raise KeyError(f"no embedding provider registered for {provider_name!r}")

        # Batch by provider's max_batch.
        batches = _chunked(texts, provider.max_batch)
        if not batches:
            batches = [list(texts)]

        # Dispatch in parallel — providers' embed calls are async.
        dim = dimensions if provider.supports_dimensions else None
        coros = [
            provider.embed(batch, model, dimensions=dim) for batch in batches
        ]
        results = await asyncio.gather(*coros)

        # Reassemble vectors in input order; sum usage across batches.
        vectors: list[list[float]] = []
        usage = Usage()
        for r in results:
            vectors.extend(r.vectors)
            usage = Usage(
                input_tokens=usage.input_tokens + r.usage.input_tokens,
                output_tokens=usage.output_tokens + r.usage.output_tokens,
                total_tokens=(usage.total_tokens or 0) + (r.usage.total_tokens or 0),
                cache_read_tokens=(
                    usage.cache_read_tokens + r.usage.cache_read_tokens
                ),
                cache_write_tokens=(
                    usage.cache_write_tokens + r.usage.cache_write_tokens
                ),
            )

        return Embeddings(
            model=model,
            provider=provider_name,
            vectors=vectors,
            usage=usage,
        )

    def _resolve(self, model: str) -> str:
        if self.provider_for_model is not None:
            return self.provider_for_model(model)
        return default_provider_for_model(model)


# ── prefix-based default resolver ────────────────────────────────────────


# Map model-id prefix → provider name. Longest prefix wins.
_DEFAULT_PREFIX_MAP: list[tuple[str, str]] = [
    ("text-embedding-3", "openai"),
    ("text-embedding-ada", "openai"),
    ("voyage-", "voyage"),
    ("embed-english", "cohere"),
    ("embed-multilingual", "cohere"),
    ("infinity:", "infinity"),
]


def default_provider_for_model(model: str) -> str:
    """Resolve a provider name from a model id by prefix."""
    # Iterate longest-prefix-first so ``text-embedding-3-small`` lands on
    # ``"openai"`` even if a shorter prefix is registered.
    candidates = sorted(_DEFAULT_PREFIX_MAP, key=lambda kv: -len(kv[0]))
    for prefix, provider in candidates:
        if model.startswith(prefix):
            return provider
    raise KeyError(f"no provider mapping for model {model!r}")


# ── helpers ──────────────────────────────────────────────────────────────


def _chunked(items: list[str], size: int) -> list[list[str]]:
    """Split ``items`` into chunks of at most ``size``."""
    if size <= 0:
        return [list(items)]
    return [items[i : i + size] for i in range(0, len(items), size)]


__all__ = [
    "EmbeddingProvider",
    "EmbeddingRouter",
    "default_provider_for_model",
]
