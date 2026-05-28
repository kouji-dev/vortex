"""I2: bundled judges — exact / regex / llm / custom."""

from __future__ import annotations

import pytest

from ai_portal.gateway.evals.judges import (
    custom_judge,
    exact_judge,
    llm_judge,
    regex_judge,
    register_custom_judge,
)
from ai_portal.gateway.evals.judges.custom import JudgeVerdict
from ai_portal.gateway.facade import (
    Actor,
    FacadeConfig,
    GatewayFacade,
    set_default_facade,
)
from ai_portal.gateway.types import (
    Capability,
    LLMRequest,
    LLMResponse,
    TextBlock,
    Usage,
)

pytestmark = pytest.mark.asyncio


# ── exact ────────────────────────────────────────────────────────────────


async def test_exact_judge_pass_after_strip_and_casefold() -> None:
    v = await exact_judge(output="  Hello  ", expected="hello")
    assert v.passed is True


async def test_exact_judge_fail_when_different() -> None:
    v = await exact_judge(output="cat", expected="dog")
    assert v.passed is False
    assert "expected" in v.detail


async def test_exact_judge_case_sensitive_flag() -> None:
    v = await exact_judge(
        output="Hello", expected="hello", config={"case_sensitive": True}
    )
    assert v.passed is False


# ── regex ────────────────────────────────────────────────────────────────


async def test_regex_judge_pass() -> None:
    v = await regex_judge(output="answer is 42", expected=r"\b\d+\b")
    assert v.passed is True


async def test_regex_judge_fail() -> None:
    v = await regex_judge(output="answer is forty-two", expected=r"\b\d+\b")
    assert v.passed is False


async def test_regex_judge_invalid_pattern_reports_error() -> None:
    v = await regex_judge(output="x", expected="[unclosed")
    assert v.passed is False
    assert "invalid regex" in v.detail


async def test_regex_judge_case_insensitive_flag() -> None:
    v = await regex_judge(output="HELLO WORLD", expected="hello", config={"flags": "i"})
    assert v.passed is True


# ── custom ───────────────────────────────────────────────────────────────


async def test_custom_judge_dispatches_by_name() -> None:
    async def _eq_len(output: str, expected: str, _config) -> JudgeVerdict:
        return JudgeVerdict(passed=len(output) == len(expected), detail="len")

    register_custom_judge("eq_len", _eq_len)
    v = await custom_judge(output="abc", expected="xyz", config={"name": "eq_len"})
    assert v.passed is True


async def test_custom_judge_unregistered_fails() -> None:
    v = await custom_judge(output="x", expected="y", config={"name": "does_not_exist"})
    assert v.passed is False
    assert "not registered" in v.detail


# ── llm (gateway-routed) ─────────────────────────────────────────────────


class _StubJudgeProvider:
    name = "stub-judge"
    capabilities: set[Capability] = {"chat"}

    def __init__(self, verdict_line: str = "PASS") -> None:
        self.verdict_line = verdict_line
        self.calls = 0

    async def complete_canonical(self, req: LLMRequest) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            id=f"j_{self.calls}",
            model_used=req.model,
            provider=self.name,
            content=[TextBlock(text=f"{self.verdict_line}\nlooks correct")],
            tool_calls=[],
            usage=Usage(input_tokens=20, output_tokens=4),
            stop_reason="end_turn",
            raw={},
        )

    async def stream_canonical(self, req: LLMRequest):  # pragma: no cover
        if False:
            yield None


def _install_facade(provider: _StubJudgeProvider):
    cfg = FacadeConfig(
        resolve_provider=lambda _req, _actor: provider,
    )
    return GatewayFacade(cfg)


async def test_llm_judge_pass_when_verdict_starts_with_pass() -> None:
    prov = _StubJudgeProvider("PASS")
    facade = _install_facade(prov)
    token = set_default_facade(facade)
    try:
        v = await llm_judge(output="x", expected="y", config={"model": "judge-1"})
        assert v.passed is True
        assert "judge=judge-1" in v.detail
        assert prov.calls == 1
    finally:
        set_default_facade(token)


async def test_llm_judge_fail_when_verdict_says_fail() -> None:
    prov = _StubJudgeProvider("FAIL")
    facade = _install_facade(prov)
    token = set_default_facade(facade)
    try:
        v = await llm_judge(
            output="x",
            expected="y",
            config={"model": "judge-1", "criteria": "factual"},
            actor=Actor(
                org_id=__import__("uuid").UUID("00000000-0000-0000-0000-000000000001"),
                kind="service",
            ),
        )
        assert v.passed is False
    finally:
        set_default_facade(token)


async def test_llm_judge_returns_failure_when_provider_raises() -> None:
    class _Boom(_StubJudgeProvider):
        async def complete_canonical(self, req):
            raise RuntimeError("boom")

    facade = _install_facade(_Boom())
    token = set_default_facade(facade)
    try:
        v = await llm_judge(output="x", expected="y")
        assert v.passed is False
        assert "judge call failed" in v.detail
    finally:
        set_default_facade(token)
