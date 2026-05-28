"""I1: PlaygroundService.run_snapshot — multi-model fan-out via facade.

Pure-unit tests. No DB required. The gateway facade is replaced via
``set_default_facade`` so the service exercises its translation of a
snapshot into one :class:`LLMRequest` per model and the assembly of the
:class:`RunResult` rows.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest

from ai_portal.gateway.facade import (
    Actor,
    FacadeConfig,
    GatewayFacade,
    set_default_facade,
)
from ai_portal.gateway.playground.service import PlaygroundService
from ai_portal.gateway.pricing import PricingSnapshot
from ai_portal.gateway.types import (
    Capability,
    Embeddings,
    LLMRequest,
    LLMResponse,
    StreamChunk,
    TextBlock,
    Usage,
)

pytestmark = pytest.mark.asyncio


# ── stubs ────────────────────────────────────────────────────────────────


class _StubProvider:
    name = "stub"
    capabilities: set[Capability] = {"chat"}

    def __init__(self) -> None:
        self.calls: list[LLMRequest] = []

    async def complete_canonical(self, req: LLMRequest) -> LLMResponse:
        self.calls.append(req)
        # Echo the user prompt back tagged with the model so multi-model
        # tests can verify per-model dispatch.
        prompt = ""
        for msg in req.messages:
            if msg.role == "user":
                for block in msg.content:
                    txt = getattr(block, "text", None)
                    if txt:
                        prompt = txt
                        break
        return LLMResponse(
            id=f"resp_{len(self.calls)}",
            model_used=req.model,
            provider=self.name,
            content=[TextBlock(text=f"[{req.model}] {prompt}")],
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

    async def embed(
        self, texts: list[str], model: str
    ) -> Embeddings:  # pragma: no cover
        raise NotImplementedError


def _install_facade(
    provider: _StubProvider | None = None,
    *,
    pricing: PricingSnapshot | None = None,
) -> tuple[GatewayFacade, _StubProvider, Any]:
    prov = provider or _StubProvider()

    cfg = FacadeConfig(
        resolve_provider=lambda _req, _actor: prov,
        resolve_pricing=lambda _model: pricing,
    )
    facade = GatewayFacade(cfg)
    token = set_default_facade(facade)
    return facade, prov, token


def _org() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-0000000000aa")


# ── tests ────────────────────────────────────────────────────────────────


async def test_run_snapshot_single_model_returns_one_result() -> None:
    _, prov, token = _install_facade()
    try:
        svc = PlaygroundService(db=None)  # type: ignore[arg-type]
        results = await svc.run_snapshot(
            org_id=_org(),
            user_id=42,
            snapshot={"prompt": "hi", "model": "gpt-4o", "temperature": 0.2},
        )
        assert len(results) == 1
        assert results[0].model == "gpt-4o"
        assert "[gpt-4o] hi" in results[0].output
        assert results[0].tokens_in == 10
        assert results[0].tokens_out == 5
        assert results[0].latency_ms >= 0
        assert prov.calls[0].temperature == 0.2
    finally:
        set_default_facade(token)


async def test_run_snapshot_multi_model_fans_out() -> None:
    _, prov, token = _install_facade()
    try:
        svc = PlaygroundService(db=None)  # type: ignore[arg-type]
        results = await svc.run_snapshot(
            org_id=_org(),
            user_id=None,
            snapshot={
                "prompt": "ping",
                "models": ["gpt-4o", "claude-sonnet-4-6", "gemini-2.5-flash"],
            },
        )
        assert [r.model for r in results] == [
            "gpt-4o",
            "claude-sonnet-4-6",
            "gemini-2.5-flash",
        ]
        # One LLMRequest per target model.
        assert len(prov.calls) == 3
        assert {c.model for c in prov.calls} == {
            "gpt-4o",
            "claude-sonnet-4-6",
            "gemini-2.5-flash",
        }
    finally:
        set_default_facade(token)


async def test_run_snapshot_includes_system_prompt() -> None:
    _, prov, token = _install_facade()
    try:
        svc = PlaygroundService(db=None)  # type: ignore[arg-type]
        await svc.run_snapshot(
            org_id=_org(),
            user_id=None,
            snapshot={
                "system": "You are concise.",
                "prompt": "Tell me a joke.",
                "model": "gpt-4o",
            },
        )
        req = prov.calls[0]
        assert req.messages[0].role == "system"
        assert req.messages[0].content[0].text == "You are concise."  # type: ignore[union-attr]
        assert req.messages[1].role == "user"
        assert req.messages[1].content[0].text == "Tell me a joke."  # type: ignore[union-attr]
    finally:
        set_default_facade(token)


async def test_run_snapshot_computes_cost_from_pricing() -> None:
    pricing = PricingSnapshot(
        price_input_per_1k_cents=30,
        price_output_per_1k_cents=60,
        price_cache_read_per_1k_cents=3,
    )
    _, _, token = _install_facade(pricing=pricing)
    try:
        svc = PlaygroundService(db=None)  # type: ignore[arg-type]
        results = await svc.run_snapshot(
            org_id=_org(),
            user_id=None,
            snapshot={"prompt": "hi", "model": "gpt-4o"},
        )
        # 10 in @30/1k + 5 out @60/1k = 0.3 + 0.3 = 0.6 cents
        assert results[0].cost_cents == pytest.approx(0.6)
    finally:
        set_default_facade(token)


async def test_run_snapshot_returns_empty_when_no_models() -> None:
    _, _, token = _install_facade()
    try:
        svc = PlaygroundService(db=None)  # type: ignore[arg-type]
        results = await svc.run_snapshot(
            org_id=_org(), user_id=None, snapshot={"prompt": "hi"}
        )
        assert results == []
    finally:
        set_default_facade(token)


async def test_run_snapshot_captures_provider_error_per_model() -> None:
    class _BoomProvider(_StubProvider):
        async def complete_canonical(self, req: LLMRequest) -> LLMResponse:
            raise RuntimeError("provider down")

    _, _, token = _install_facade(provider=_BoomProvider())
    try:
        svc = PlaygroundService(db=None)  # type: ignore[arg-type]
        results = await svc.run_snapshot(
            org_id=_org(),
            user_id=None,
            snapshot={"prompt": "hi", "model": "gpt-4o"},
        )
        assert len(results) == 1
        assert results[0].error is not None
        assert "provider down" in results[0].error
        assert results[0].output == ""
    finally:
        set_default_facade(token)


async def test_actor_construction_in_run_snapshot() -> None:
    # Sanity check on Actor instantiation paths used inside the service.
    a = Actor(org_id=_org(), user_id=1, kind="user")
    assert a.org_id == _org()
    assert a.user_id == 1
