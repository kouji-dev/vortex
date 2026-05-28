"""G1: per-request cost calculation.

Cost (in cents) = (tokens_in × price_in + tokens_out × price_out
+ tokens_cache_read × price_cache_read) / 1_000.

Cache reads typically charge a fraction of input rate; we use the
``price_cache_read_per_1k_cents`` column from the GatewayModel snapshot.

The gateway service exposes the computed cost on the response via a header
(``x-gateway-cost-cents``) and via the trace row.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from ai_portal.gateway.policies import complete_with_policies
from ai_portal.gateway.pricing import (
    PricingSnapshot,
    compute_cost_cents,
)
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


# ── unit: compute_cost_cents ────────────────────────────────────────────────


def test_compute_cost_cents_basic() -> None:
    """input 1000 tok @ 30 cents/1k + output 500 tok @ 60 cents/1k = 30 + 30 = 60."""
    pricing = PricingSnapshot(
        price_input_per_1k_cents=30,
        price_output_per_1k_cents=60,
        price_cache_read_per_1k_cents=3,
    )
    usage = Usage(input_tokens=1000, output_tokens=500)
    assert compute_cost_cents(usage, pricing) == pytest.approx(60.0)


def test_compute_cost_cents_with_cache_reads() -> None:
    """Cache reads charged at cache_read rate not input rate."""
    pricing = PricingSnapshot(
        price_input_per_1k_cents=100,
        price_output_per_1k_cents=200,
        price_cache_read_per_1k_cents=10,
    )
    usage = Usage(
        input_tokens=1000,
        output_tokens=1000,
        cache_read_tokens=2000,
    )
    # 100 + 200 + 20 = 320
    assert compute_cost_cents(usage, pricing) == pytest.approx(320.0)


def test_compute_cost_cents_zero_pricing_returns_zero() -> None:
    pricing = PricingSnapshot(
        price_input_per_1k_cents=0,
        price_output_per_1k_cents=0,
        price_cache_read_per_1k_cents=0,
    )
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert compute_cost_cents(usage, pricing) == 0.0


def test_compute_cost_cents_fractional() -> None:
    """Sub-1k token counts are properly scaled."""
    pricing = PricingSnapshot(
        price_input_per_1k_cents=10,
        price_output_per_1k_cents=20,
        price_cache_read_per_1k_cents=1,
    )
    usage = Usage(input_tokens=250, output_tokens=100)
    # 0.25 * 10 + 0.1 * 20 = 2.5 + 2.0 = 4.5
    assert compute_cost_cents(usage, pricing) == pytest.approx(4.5)


# ── integration: response header ────────────────────────────────────────────


class _StubProvider:
    name = "stub"
    capabilities: set[Capability] = {"chat"}

    async def complete_canonical(self, req: LLMRequest) -> LLMResponse:
        return LLMResponse(
            id="resp_1",
            model_used=req.model,
            provider=self.name,
            content=[TextBlock(text="ok")],
            tool_calls=[],
            usage=Usage(input_tokens=1000, output_tokens=500),
            stop_reason="end_turn",
            raw={},
        )

    async def stream_canonical(self, req: LLMRequest) -> AsyncIterator[StreamChunk]:
        if False:  # pragma: no cover
            yield StreamChunk.model_validate({"type": "text_delta", "text": ""})

    async def embed(self, texts, model):  # pragma: no cover
        raise NotImplementedError


async def test_complete_with_policies_returns_cost_header() -> None:
    pricing = PricingSnapshot(
        price_input_per_1k_cents=30,
        price_output_per_1k_cents=60,
        price_cache_read_per_1k_cents=3,
    )
    req = LLMRequest(
        model="m",
        messages=[Message(role="user", content=[TextBlock(text="hi")])],
    )
    result = await complete_with_policies(req, _StubProvider(), pricing=pricing)
    # 1000 tok input @ 30¢/1k + 500 tok out @ 60¢/1k = 60.0
    assert result.cost_cents == pytest.approx(60.0)
    assert result.headers["x-gateway-cost-cents"] == "60.000000"
    assert result.response.usage.input_tokens == 1000
    assert result.cache_hit is False
