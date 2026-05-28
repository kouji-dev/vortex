"""C2: failover policy — retry primary then fall to subsequent candidates.

The :class:`Failover` wraps any ``call(candidate) -> result`` async function
and a list of candidates produced by the routing strategy. It retries on
known transient errors (5xx, 429, timeout) with exponential backoff +
jitter and updates the circuit breaker for the failing provider.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from ai_portal.gateway.routing.circuit_breaker import CircuitBreaker
from ai_portal.gateway.routing.failover import (
    Failover,
    FailoverExhausted,
    ProviderHTTPError,
    ProviderTimeoutError,
)
from ai_portal.gateway.routing.protocol import ProviderModel


@dataclass
class _Resp:
    body: str
    chosen: str


def _cands() -> list[ProviderModel]:
    return [
        ProviderModel(provider="anthropic", model_id="claude-sonnet-4-6"),
        ProviderModel(provider="openai", model_id="gpt-4o"),
        ProviderModel(provider="gemini", model_id="gemini-2.5-flash"),
    ]


async def _ok(c: ProviderModel) -> _Resp:
    return _Resp(body=f"ok-{c.provider}", chosen=c.provider)


async def _always_503(c: ProviderModel) -> _Resp:
    raise ProviderHTTPError(status=503, message="upstream down", provider=c.provider)


def _make_failover(**kwargs) -> Failover:
    # No jitter + zero backoff in tests for determinism.
    return Failover(
        max_attempts_per_candidate=1,
        base_backoff_seconds=0.0,
        max_backoff_seconds=0.0,
        jitter=0.0,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_primary_succeeds_returns_immediately():
    fo = _make_failover()
    res = await fo.execute(_cands(), _ok)
    assert res.chosen == "anthropic"


@pytest.mark.asyncio
async def test_503_on_primary_falls_to_next_candidate():
    calls: list[str] = []

    async def call(c: ProviderModel) -> _Resp:
        calls.append(c.provider)
        if c.provider == "anthropic":
            raise ProviderHTTPError(503, "boom", provider=c.provider)
        return await _ok(c)

    fo = _make_failover()
    res = await fo.execute(_cands(), call)
    assert res.chosen == "openai"
    assert calls == ["anthropic", "openai"]


@pytest.mark.asyncio
async def test_429_triggers_failover():
    async def call(c: ProviderModel) -> _Resp:
        if c.provider == "anthropic":
            raise ProviderHTTPError(429, "rate limited", provider=c.provider)
        return await _ok(c)

    fo = _make_failover()
    res = await fo.execute(_cands(), call)
    assert res.chosen == "openai"


@pytest.mark.asyncio
async def test_timeout_triggers_failover():
    async def call(c: ProviderModel) -> _Resp:
        if c.provider == "anthropic":
            raise ProviderTimeoutError(provider=c.provider)
        return await _ok(c)

    fo = _make_failover()
    res = await fo.execute(_cands(), call)
    assert res.chosen == "openai"


@pytest.mark.asyncio
async def test_4xx_other_than_429_does_not_failover():
    """A 400 is a client error — not a transient upstream issue."""

    async def call(c: ProviderModel) -> _Resp:
        raise ProviderHTTPError(400, "bad request", provider=c.provider)

    fo = _make_failover()
    with pytest.raises(ProviderHTTPError) as exc:
        await fo.execute(_cands(), call)
    assert exc.value.status == 400
    # Should only have tried the first.
    assert exc.value.provider == "anthropic"


@pytest.mark.asyncio
async def test_all_candidates_failing_raises_exhausted():
    fo = _make_failover()
    with pytest.raises(FailoverExhausted) as exc:
        await fo.execute(_cands(), _always_503)
    assert len(exc.value.attempts) == 3  # one attempt per candidate


@pytest.mark.asyncio
async def test_retry_within_same_candidate_then_failover():
    """``max_attempts_per_candidate=2``: anthropic 503 twice then openai OK."""
    counts: dict[str, int] = {}

    async def call(c: ProviderModel) -> _Resp:
        counts[c.provider] = counts.get(c.provider, 0) + 1
        if c.provider == "anthropic":
            raise ProviderHTTPError(503, "boom", provider=c.provider)
        return await _ok(c)

    fo = Failover(
        max_attempts_per_candidate=2,
        base_backoff_seconds=0.0,
        max_backoff_seconds=0.0,
        jitter=0.0,
    )
    res = await fo.execute(_cands(), call)
    assert res.chosen == "openai"
    assert counts["anthropic"] == 2
    assert counts["openai"] == 1


@pytest.mark.asyncio
async def test_circuit_breaker_skips_open_candidates():
    cb = CircuitBreaker(failure_threshold=1, recovery_seconds=60, now=lambda: 0.0)
    # Pre-open the anthropic circuit.
    cb.record_failure("anthropic:claude-sonnet-4-6")

    seen: list[str] = []

    async def call(c: ProviderModel) -> _Resp:
        seen.append(c.provider)
        return await _ok(c)

    fo = Failover(
        max_attempts_per_candidate=1,
        base_backoff_seconds=0.0,
        max_backoff_seconds=0.0,
        jitter=0.0,
        circuit_breaker=cb,
    )
    res = await fo.execute(_cands(), call)
    assert seen == ["openai"]  # anthropic skipped — circuit open.
    assert res.chosen == "openai"


@pytest.mark.asyncio
async def test_failover_records_failures_to_circuit_breaker():
    cb = CircuitBreaker(failure_threshold=1, recovery_seconds=60, now=lambda: 0.0)

    async def call(c: ProviderModel) -> _Resp:
        if c.provider == "anthropic":
            raise ProviderHTTPError(503, "boom", provider=c.provider)
        return await _ok(c)

    fo = Failover(
        max_attempts_per_candidate=1,
        base_backoff_seconds=0.0,
        max_backoff_seconds=0.0,
        jitter=0.0,
        circuit_breaker=cb,
    )
    await fo.execute(_cands(), call)
    # Anthropic should now have an open circuit.
    from ai_portal.gateway.routing.circuit_breaker import CircuitState

    assert cb.state("anthropic:claude-sonnet-4-6") is CircuitState.OPEN


@pytest.mark.asyncio
async def test_backoff_is_called_between_attempts(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def call(c: ProviderModel) -> _Resp:
        raise ProviderHTTPError(503, "boom", provider=c.provider)

    fo = Failover(
        max_attempts_per_candidate=2,
        base_backoff_seconds=0.1,
        max_backoff_seconds=1.0,
        jitter=0.0,
    )
    with pytest.raises(FailoverExhausted):
        await fo.execute(_cands(), call)
    # 3 candidates × 2 attempts = 6 calls; backoff between every retry attempt
    # (within candidate) and between candidates → at least 5 sleeps.
    assert len(sleeps) >= 5
    # All sleeps within the configured window.
    assert all(0.0 <= s <= 1.0 for s in sleeps)
