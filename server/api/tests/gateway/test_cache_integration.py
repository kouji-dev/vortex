"""E2: cache integration in gateway completion path.

Behavior:
- First call: provider invoked; response stored in cache; ``cache_hit`` flag
  False on the trace; ``x-gateway-cache-hit`` header = ``"false"``.
- Second identical call within TTL: provider NOT invoked; response returned
  from cache; ``cache_hit`` True; ``x-gateway-cache-hit`` header = ``"true"``;
  ``on_cache_hit_usage`` callback fires with ``tokens_cache_read`` set.
- Different request body → different cache key → no hit.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from ai_portal.gateway.cache.backends.inmemory import InMemoryCache
from ai_portal.gateway.policies import (
    complete_with_policies,
    compute_request_hash,
)
from ai_portal.gateway.pricing import PricingSnapshot
from ai_portal.gateway.types import (
    Capability,
    LLMRequest,
    LLMResponse,
    Message,
    StreamChunk,
    TextBlock,
    Usage,
)

pytestmark = pytest.mark.asyncio


# ── stubs ────────────────────────────────────────────────────────────────


class _CountingProvider:
    name = "stub"
    capabilities: set[Capability] = {"chat"}

    def __init__(self) -> None:
        self.calls = 0

    async def complete_canonical(self, req: LLMRequest) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            id=f"resp_{self.calls}",
            model_used=req.model,
            provider=self.name,
            content=[TextBlock(text=f"reply #{self.calls}")],
            tool_calls=[],
            usage=Usage(input_tokens=42, output_tokens=10),
            stop_reason="end_turn",
            raw={},
        )

    async def stream_canonical(
        self, req: LLMRequest
    ) -> AsyncIterator[StreamChunk]:  # pragma: no cover
        if False:
            yield StreamChunk.model_validate({"type": "text_delta", "text": ""})

    async def embed(self, texts, model):  # pragma: no cover
        raise NotImplementedError


def _req(text: str = "hello") -> LLMRequest:
    return LLMRequest(
        model="m",
        messages=[Message(role="user", content=[TextBlock(text=text)])],
    )


# ── tests ─────────────────────────────────────────────────────────────────


async def test_cache_hit_returns_cached_response_without_dispatch() -> None:
    cache = InMemoryCache()
    provider = _CountingProvider()
    req = _req()

    # First call — miss → provider invoked → cached.
    first = await complete_with_policies(
        req, provider, cache=cache, cache_ttl_seconds=60
    )
    assert provider.calls == 1
    assert first.cache_hit is False
    assert first.headers["x-gateway-cache-hit"] == "false"

    # Second identical call — hit → provider NOT invoked.
    second = await complete_with_policies(
        req, provider, cache=cache, cache_ttl_seconds=60
    )
    assert provider.calls == 1  # unchanged
    assert second.cache_hit is True
    assert second.headers["x-gateway-cache-hit"] == "true"
    assert second.headers["x-gateway-cost-cents"] == "0.000000"
    assert second.response.content == first.response.content


async def test_cache_hit_emits_cache_read_usage() -> None:
    cache = InMemoryCache()
    provider = _CountingProvider()
    req = _req()

    captured: dict[str, object] = {}

    def emitter(*, tokens_cache_read: int, model: str) -> None:
        captured["tokens_cache_read"] = tokens_cache_read
        captured["model"] = model

    # Prime the cache.
    await complete_with_policies(req, provider, cache=cache)

    # Hit triggers usage callback.
    result = await complete_with_policies(
        req, provider, cache=cache, on_cache_hit_usage=emitter
    )
    assert result.cache_hit is True
    # First call recorded 42 input tokens — the hit charges those as cache_read.
    assert captured["tokens_cache_read"] == 42
    assert captured["model"] == "m"


async def test_different_requests_have_different_cache_keys() -> None:
    cache = InMemoryCache()
    provider = _CountingProvider()

    await complete_with_policies(_req("hello"), provider, cache=cache)
    await complete_with_policies(_req("world"), provider, cache=cache)
    # Two distinct prompts → two provider hits.
    assert provider.calls == 2


async def test_cache_hit_trace_extra_marks_cache_read_tokens() -> None:
    cache = InMemoryCache()
    provider = _CountingProvider()
    req = _req()

    await complete_with_policies(req, provider, cache=cache)
    result = await complete_with_policies(req, provider, cache=cache)
    assert result.trace_extra["cache_hit"] is True
    assert result.trace_extra["tokens_cache_read"] == 42
    assert result.trace_extra["tokens_in"] == 0
    assert result.trace_extra["tokens_out"] == 0


async def test_request_hash_stable_across_calls() -> None:
    """The cache key must not change for an identical request."""
    a = compute_request_hash(_req())
    b = compute_request_hash(_req())
    assert a == b
    c = compute_request_hash(_req("different"))
    assert c != a


async def test_cache_hit_cost_is_zero_even_with_pricing() -> None:
    """A cache hit charges no cost even when pricing snapshot present."""
    cache = InMemoryCache()
    provider = _CountingProvider()
    pricing = PricingSnapshot(
        price_input_per_1k_cents=1000,
        price_output_per_1k_cents=2000,
        price_cache_read_per_1k_cents=10,
    )
    req = _req()
    await complete_with_policies(req, provider, cache=cache, pricing=pricing)
    hit = await complete_with_policies(
        req, provider, cache=cache, pricing=pricing
    )
    assert hit.cache_hit is True
    assert hit.cost_cents == 0.0
