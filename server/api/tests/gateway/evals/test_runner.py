"""I2: EvalRunner — run a test set across N target models.

Verifies the spec test: 3 records, judge=``exact``, run against 2 models →
results with ``pass_rate``, ``p95_latency_ms``, ``cost``. Also covers
regression detection.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest

from ai_portal.gateway.evals.runner import EvalRunner, make_actor_for_run
from ai_portal.gateway.evals.schemas import EvalRecord, EvalRunSummary
from ai_portal.gateway.facade import (
    FacadeConfig,
    GatewayFacade,
    set_default_facade,
)
from ai_portal.gateway.pricing import PricingSnapshot
from ai_portal.gateway.types import (
    Capability,
    LLMRequest,
    LLMResponse,
    StreamChunk,
    TextBlock,
    Usage,
)

pytestmark = pytest.mark.asyncio


# ── stub provider ────────────────────────────────────────────────────────


class _ScriptedProvider:
    """Returns the value mapped from input.

    ``script`` is ``{(model, input_text): output_text}``. Missing entries
    return ``""``.
    """

    name = "scripted"
    capabilities: set[Capability] = {"chat"}

    def __init__(self, script: dict[tuple[str, str], str]) -> None:
        self.script = script
        self.calls = 0

    def _input_text(self, req: LLMRequest) -> str:
        for msg in req.messages:
            if msg.role == "user":
                for block in msg.content:
                    t = getattr(block, "text", None)
                    if t:
                        return t
        return ""

    async def complete_canonical(self, req: LLMRequest) -> LLMResponse:
        self.calls += 1
        out = self.script.get((req.model, self._input_text(req)), "")
        return LLMResponse(
            id=f"r_{self.calls}",
            model_used=req.model,
            provider=self.name,
            content=[TextBlock(text=out)],
            tool_calls=[],
            usage=Usage(input_tokens=10, output_tokens=2),
            stop_reason="end_turn",
            raw={},
        )

    async def stream_canonical(
        self, req: LLMRequest
    ) -> AsyncIterator[StreamChunk]:  # pragma: no cover
        if False:
            yield StreamChunk.model_validate({"type": "text_delta", "text": ""})


def _install_facade(provider, *, pricing: PricingSnapshot | None = None):
    cfg = FacadeConfig(
        resolve_provider=lambda _req, _actor: provider,
        resolve_pricing=lambda _model: pricing,
    )
    facade = GatewayFacade(cfg)
    return set_default_facade(facade)


def _actor():
    return make_actor_for_run(
        org_id=uuid.UUID("00000000-0000-0000-0000-0000000000aa"),
        user_id=1,
    )


def _records() -> list[EvalRecord]:
    return [
        EvalRecord(id="r1", input="2+2=", expected="4", judge="exact"),
        EvalRecord(id="r2", input="3+3=", expected="6", judge="exact"),
        EvalRecord(id="r3", input="capital of France", expected="Paris", judge="exact"),
    ]


# ── spec test ────────────────────────────────────────────────────────────


async def test_runner_three_records_two_models_reports_aggregates() -> None:
    script = {
        ("gpt-4o", "2+2="): "4",
        ("gpt-4o", "3+3="): "6",
        ("gpt-4o", "capital of France"): "Paris",
        # Sonnet gets one wrong (regression test bed).
        ("claude-sonnet-4-6", "2+2="): "4",
        ("claude-sonnet-4-6", "3+3="): "wrong",
        ("claude-sonnet-4-6", "capital of France"): "Paris",
    }
    pricing = PricingSnapshot(
        price_input_per_1k_cents=30,
        price_output_per_1k_cents=60,
        price_cache_read_per_1k_cents=3,
    )
    token = _install_facade(_ScriptedProvider(script), pricing=pricing)
    try:
        runner = EvalRunner()
        outcomes = await runner.run_all(
            records=_records(),
            target_models=["gpt-4o", "claude-sonnet-4-6"],
            actor=_actor(),
        )
        assert len(outcomes) == 2

        s_gpt = next(o.summary for o in outcomes if o.target_model == "gpt-4o")
        assert s_gpt.n == 3
        assert s_gpt.passed == 3
        assert s_gpt.failed == 0
        assert s_gpt.pass_rate == pytest.approx(1.0)
        assert s_gpt.p95_latency_ms >= 0
        # 3 records × (10 in @ 30 + 2 out @ 60) per 1k = 3 × 0.42 = 1.26 cents
        assert s_gpt.total_cost_cents == pytest.approx(1.26, rel=0.01)

        s_son = next(
            o.summary for o in outcomes if o.target_model == "claude-sonnet-4-6"
        )
        assert s_son.passed == 2
        assert s_son.failed == 1
        assert s_son.pass_rate == pytest.approx(2 / 3, rel=0.01)
    finally:
        set_default_facade(token)


# ── regression detection ─────────────────────────────────────────────────


async def test_regression_detected_when_pass_rate_drops_more_than_threshold() -> None:
    token = _install_facade(_ScriptedProvider({}))
    try:
        runner = EvalRunner(regression_threshold=0.05)
        prev = EvalRunSummary(target_model="m", pass_rate=0.9, n=10, passed=9, failed=1)
        curr = EvalRunSummary(target_model="m", pass_rate=0.7, n=10, passed=7, failed=3)
        out = runner.detect_regression(current=curr, previous=prev)
        assert out.regression is True
        assert out.regression_delta == pytest.approx(-0.2)
    finally:
        set_default_facade(token)


async def test_no_regression_when_drop_within_threshold() -> None:
    token = _install_facade(_ScriptedProvider({}))
    try:
        runner = EvalRunner(regression_threshold=0.05)
        prev = EvalRunSummary(target_model="m", pass_rate=0.9, n=10, passed=9, failed=1)
        curr = EvalRunSummary(
            target_model="m", pass_rate=0.87, n=10, passed=8, failed=2
        )
        out = runner.detect_regression(current=curr, previous=prev)
        assert out.regression is False
    finally:
        set_default_facade(token)


async def test_no_regression_when_no_previous_run() -> None:
    token = _install_facade(_ScriptedProvider({}))
    try:
        runner = EvalRunner()
        curr = EvalRunSummary(target_model="m", pass_rate=0.5, n=2, passed=1, failed=1)
        out = runner.detect_regression(current=curr, previous=None)
        assert out.regression is False
        assert out.regression_delta == 0.0
    finally:
        set_default_facade(token)


# ── provider error path ─────────────────────────────────────────────────


async def test_record_marked_failed_when_provider_raises() -> None:
    class _BoomProvider(_ScriptedProvider):
        async def complete_canonical(self, req):
            raise RuntimeError("upstream down")

    token = _install_facade(_BoomProvider({}))
    try:
        runner = EvalRunner()
        outcome = await runner.run(
            records=[EvalRecord(id="r1", input="x", expected="y", judge="exact")],
            target_model="m",
            actor=_actor(),
        )
        assert outcome.summary.failed == 1
        assert outcome.results[0].passed is False
        assert outcome.results[0].error is not None
        assert "upstream down" in outcome.results[0].error
    finally:
        set_default_facade(token)


# ── regex + multi-judge mix ─────────────────────────────────────────────


async def test_runner_supports_mixed_judges_in_single_test_set() -> None:
    script = {
        ("m", "give me a digit"): "the answer is 7",
        ("m", "say hi"): "hello",
    }
    token = _install_facade(_ScriptedProvider(script))
    try:
        runner = EvalRunner()
        records = [
            EvalRecord(
                id="r1", input="give me a digit", expected=r"\b\d\b", judge="regex"
            ),
            EvalRecord(id="r2", input="say hi", expected="hello", judge="exact"),
        ]
        outcome = await runner.run(records=records, target_model="m", actor=_actor())
        assert outcome.summary.passed == 2
        assert outcome.summary.pass_rate == pytest.approx(1.0)
    finally:
        set_default_facade(token)
