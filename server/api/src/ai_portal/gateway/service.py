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

from ai_portal.gateway.cache.protocol import Cache
from ai_portal.gateway.pricing import PricingSnapshot
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


# ── policy context (G1/G2/E2) ───────────────────────────────────────────────


class PolicyContext:
    """Bundle of optional cross-cutting policy hooks applied to every call.

    Attached via the :func:`get_policy_context` FastAPI dep. The default
    instance (returned when no override is registered) is a no-op: no
    pricing, no budget check, no cache. Production wiring overrides the dep
    in ``main.py``; tests override per-suite.
    """

    __slots__ = (
        "budget_check",
        "cache",
        "cache_ttl_seconds",
        "estimated_cost_usd",
        "on_cache_hit_usage",
        "pricing",
    )

    def __init__(
        self,
        *,
        pricing: PricingSnapshot | None = None,
        cache: Cache | None = None,
        cache_ttl_seconds: int = 300,
        budget_check: object | None = None,
        estimated_cost_usd: float = 0.0,
        on_cache_hit_usage: object | None = None,
    ) -> None:
        self.pricing = pricing
        self.cache = cache
        self.cache_ttl_seconds = cache_ttl_seconds
        self.budget_check = budget_check
        self.estimated_cost_usd = estimated_cost_usd
        self.on_cache_hit_usage = on_cache_hit_usage


def get_policy_context() -> PolicyContext:
    """FastAPI dep — yields the active :class:`PolicyContext`.

    Default returns an empty context (no policies). Tests / production
    override this dep to inject pricing / cache / budget hooks.
    """
    return PolicyContext()


__all__ = [
    "PolicyContext",
    "complete",
    "embed",
    "get_llm_provider",
    "get_policy_context",
    "stream",
]
