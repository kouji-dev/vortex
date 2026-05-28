"""Gateway dispatch service — minimal facade for the compat surfaces.

Provides:

- :func:`get_llm_provider` — FastAPI dep that resolves the active provider.
  Tests override this dep with a fake provider. Future routing / failover /
  guardrails / cache logic will land here.
- :func:`complete` / :func:`stream` / :func:`embed` — thin async wrappers that
  delegate to the provider's canonical protocol methods.

This is intentionally tiny. Phase C (routing) + Phase E (cache) + Phase F
(guardrails) hook in by replacing :func:`get_llm_provider` and wrapping the
provider call in this module.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from ai_portal.gateway.types import (
    Capability,
    Embeddings,
    LLMRequest,
    LLMResponse,
    StreamChunk,
)


@runtime_checkable
class _ProviderLike(Protocol):
    """Structural shape the gateway needs from a provider.

    Matches :class:`ai_portal.catalog.providers.protocol.LLMProvider` but
    declared here as a Protocol to avoid an import cycle and to let tests
    inject lightweight fakes without inheriting from the full LLMProvider.
    """

    name: str
    capabilities: set[Capability]

    async def complete_canonical(self, req: LLMRequest) -> LLMResponse: ...
    async def stream_canonical(self, req: LLMRequest) -> AsyncIterator[StreamChunk]: ...
    async def embed(self, texts: list[str], model: str) -> Embeddings: ...


def get_llm_provider() -> _ProviderLike:
    """FastAPI dep — yields the LLMProvider that will service the request.

    The default raises so production wiring is forced to override this dep
    (routing/credentials live in higher phases). Tests override with a fake.
    """
    raise RuntimeError(
        "no LLMProvider bound — override `get_llm_provider` in tests or wire "
        "routing.resolve_provider() in production startup."
    )


async def complete(req: LLMRequest, provider: _ProviderLike) -> LLMResponse:
    """Non-streaming completion dispatch."""
    return await provider.complete_canonical(req)


async def stream(
    req: LLMRequest, provider: _ProviderLike
) -> AsyncIterator[StreamChunk]:
    """Streaming completion dispatch."""
    async for chunk in provider.stream_canonical(req):
        yield chunk


async def embed(
    texts: list[str], model: str, provider: _ProviderLike
) -> Embeddings:
    """Embeddings dispatch."""
    return await provider.embed(texts, model)


__all__ = [
    "complete",
    "embed",
    "get_llm_provider",
    "stream",
]
