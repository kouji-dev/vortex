"""G2: pre-call budget cutoff.

When ``check_budget`` returns ``is_blocked=True``, the gateway aborts the
call with a :class:`BudgetExceeded` error carrying headers for a 402
response. When the check passes, the policy result includes the action via
``x-gateway-budget-status``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest

from ai_portal.gateway.policies import (
    BudgetExceeded,
    complete_with_policies,
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


class _StubProvider:
    name = "stub"
    capabilities: set[Capability] = {"chat"}
    called = False

    async def complete_canonical(self, req: LLMRequest) -> LLMResponse:
        type(self).called = True
        return LLMResponse(
            id="resp_1",
            model_used=req.model,
            provider=self.name,
            content=[TextBlock(text="ok")],
            tool_calls=[],
            usage=Usage(input_tokens=10, output_tokens=5),
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


@dataclass
class _Decision:
    is_blocked: bool
    reason: str = ""
    action: str = "allow"


def _req() -> LLMRequest:
    return LLMRequest(
        model="m",
        messages=[Message(role="user", content=[TextBlock(text="hi")])],
    )


# ── tests ─────────────────────────────────────────────────────────────────


async def test_budget_block_raises_and_skips_provider() -> None:
    provider = _StubProvider()
    type(provider).called = False

    def check(*, incoming_cost_usd: float) -> _Decision:
        return _Decision(is_blocked=True, reason="monthly budget exceeded", action="block")

    with pytest.raises(BudgetExceeded) as exc_info:
        await complete_with_policies(
            _req(),
            provider,
            budget_check=check,
            estimated_cost_usd=0.05,
            pricing=PricingSnapshot(),
        )

    err = exc_info.value
    assert "monthly budget exceeded" in err.reason
    assert err.headers["x-gateway-budget-status"] == "blocked"
    assert err.headers["x-gateway-budget-reason"] == "monthly budget exceeded"
    assert provider.called is False  # provider never reached


async def test_budget_allow_attaches_status_header() -> None:
    provider = _StubProvider()
    type(provider).called = False

    def check(*, incoming_cost_usd: float) -> _Decision:
        return _Decision(is_blocked=False, reason="", action="allow")

    result = await complete_with_policies(
        _req(),
        provider,
        budget_check=check,
        estimated_cost_usd=0.001,
        pricing=PricingSnapshot(),
    )
    assert provider.called is True
    assert result.headers["x-gateway-budget-status"] == "allow"


async def test_budget_warn_passes_through() -> None:
    """Warn action allows the call but surfaces a header for ops visibility."""
    provider = _StubProvider()
    type(provider).called = False

    def check(*, incoming_cost_usd: float) -> _Decision:
        return _Decision(is_blocked=False, reason="80% reached", action="warn")

    result = await complete_with_policies(
        _req(),
        provider,
        budget_check=check,
        pricing=PricingSnapshot(),
    )
    assert provider.called is True
    assert result.headers["x-gateway-budget-status"] == "warn"


# ── HTTP-level integration: OpenAI compat returns 402 on budget block ───────


def test_openai_compat_returns_402_on_budget_block() -> None:
    """Compat endpoint translates BudgetExceeded into 402 + header."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ai_portal.gateway.compat.openai import router as openai_router
    from ai_portal.gateway.service import (
        PolicyContext,
        get_llm_provider,
        get_policy_context,
    )

    provider = _StubProvider()
    type(provider).called = False

    def check(*, incoming_cost_usd: float) -> _Decision:
        return _Decision(is_blocked=True, reason="cap reached", action="block")

    ctx = PolicyContext(budget_check=check, pricing=PricingSnapshot())

    app = FastAPI()
    app.include_router(openai_router)
    app.dependency_overrides[get_llm_provider] = lambda: provider
    app.dependency_overrides[get_policy_context] = lambda: ctx
    client = TestClient(app)

    res = client.post(
        "/v1/chat/completions",
        json={
            "model": "m",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert res.status_code == 402
    assert res.headers.get("x-gateway-budget-status") == "blocked"
    assert "cap reached" in res.headers.get("x-gateway-budget-reason", "")
    assert provider.called is False


def test_openai_compat_includes_cost_header() -> None:
    """When pricing is wired, response includes ``x-gateway-cost-cents``."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ai_portal.gateway.compat.openai import router as openai_router
    from ai_portal.gateway.service import (
        PolicyContext,
        get_llm_provider,
        get_policy_context,
    )

    pricing = PricingSnapshot(
        price_input_per_1k_cents=100,
        price_output_per_1k_cents=200,
        price_cache_read_per_1k_cents=10,
    )
    ctx = PolicyContext(pricing=pricing)
    provider = _StubProvider()

    app = FastAPI()
    app.include_router(openai_router)
    app.dependency_overrides[get_llm_provider] = lambda: provider
    app.dependency_overrides[get_policy_context] = lambda: ctx
    client = TestClient(app)

    res = client.post(
        "/v1/chat/completions",
        json={
            "model": "m",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert res.status_code == 200
    # 10 tok in * 100¢/1k + 5 tok out * 200¢/1k = 1.0 + 1.0 = 2.0
    assert res.headers["x-gateway-cost-cents"] == "2.000000"
    assert res.headers["x-gateway-cache-hit"] == "false"
