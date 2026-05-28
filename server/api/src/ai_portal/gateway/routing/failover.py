"""Failover policy for gateway routing.

Wraps a list of :class:`ProviderModel` candidates and a ``call(candidate)``
coroutine. Tries each candidate in order; on a *transient* provider error
(5xx, 429, timeout) backs off and retries up to
``max_attempts_per_candidate`` times, then moves to the next candidate.

Non-transient errors (most 4xx) re-raise immediately so callers see proper
client errors.

The failover loop also drives a :class:`CircuitBreaker`: each candidate's
``(provider, model_id)`` key is checked before the attempt and updated
based on outcome.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

from ai_portal.gateway.routing.circuit_breaker import (
    CircuitBreaker,
    CircuitOpen,
)
from ai_portal.gateway.routing.protocol import ProviderModel

T = TypeVar("T")


# ── exceptions ──────────────────────────────────────────────────────────────


class ProviderHTTPError(Exception):
    """Wire-level HTTP failure from a provider call."""

    def __init__(
        self, status: int, message: str = "", *, provider: str | None = None
    ) -> None:
        self.status = int(status)
        self.provider = provider
        super().__init__(f"HTTP {status} from {provider}: {message}")


class ProviderTimeoutError(Exception):
    """Provider call timed out."""

    def __init__(self, *, provider: str | None = None) -> None:
        self.provider = provider
        super().__init__(f"timeout from {provider}")


@dataclass(frozen=True)
class Attempt:
    candidate: ProviderModel
    error: Exception


@dataclass
class FailoverExhausted(Exception):
    """Raised when every candidate fails."""

    attempts: list[Attempt]

    def __post_init__(self) -> None:
        msg = "; ".join(
            f"{a.candidate.provider}/{a.candidate.model_id}: {a.error}"
            for a in self.attempts
        )
        super().__init__(f"all candidates exhausted: {msg}")


def _candidate_key(c: ProviderModel) -> str:
    return f"{c.provider}:{c.model_id}"


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, ProviderTimeoutError):
        return True
    if isinstance(exc, asyncio.TimeoutError | TimeoutError):
        return True
    if isinstance(exc, ProviderHTTPError):
        return exc.status >= 500 or exc.status == 429
    return False


# ── failover orchestrator ───────────────────────────────────────────────────


@dataclass
class Failover:
    """Resilient call orchestrator.

    Args:
        max_attempts_per_candidate: How many times to retry a single
            candidate before moving on. ``1`` = no in-candidate retry.
        base_backoff_seconds: Base of the exponential backoff
            (``base * 2 ** attempt``).
        max_backoff_seconds: Cap.
        jitter: Multiplicative jitter factor; the actual sleep is
            ``backoff * (1 - jitter + 2*jitter*random())``. ``0.0`` = no
            jitter (deterministic).
        circuit_breaker: Optional shared breaker. If supplied, candidates
            with an open circuit are skipped, and failures are recorded.
    """

    max_attempts_per_candidate: int = 1
    base_backoff_seconds: float = 0.2
    max_backoff_seconds: float = 2.0
    jitter: float = 0.25
    circuit_breaker: CircuitBreaker | None = None
    _rng: random.Random = field(default_factory=random.Random)

    async def execute(
        self,
        candidates: list[ProviderModel],
        call: Callable[[ProviderModel], Awaitable[T]],
    ) -> T:
        if not candidates:
            raise FailoverExhausted(attempts=[])
        attempts: list[Attempt] = []
        for idx, c in enumerate(candidates):
            key = _candidate_key(c)
            cb = self.circuit_breaker
            if cb is not None:
                try:
                    cb.allow(key)
                except CircuitOpen as exc:
                    attempts.append(Attempt(candidate=c, error=exc))
                    if idx < len(candidates) - 1:
                        await self._sleep(0)
                    continue
            last_exc: Exception | None = None
            for attempt in range(self.max_attempts_per_candidate):
                try:
                    result = await call(c)
                except Exception as exc:  # noqa: BLE001 — propagate non-transient.
                    last_exc = exc
                    if not _is_transient(exc):
                        if cb is not None:
                            cb.record_failure(key)
                        raise
                    if attempt + 1 < self.max_attempts_per_candidate:
                        await self._backoff(attempt)
                        continue
                    break
                else:
                    if cb is not None:
                        cb.record_success(key)
                    return result
            if last_exc is not None:
                attempts.append(Attempt(candidate=c, error=last_exc))
                if cb is not None:
                    cb.record_failure(key)
            # Backoff between candidates (except after the last).
            if idx < len(candidates) - 1:
                await self._backoff(0)
        raise FailoverExhausted(attempts=attempts)

    # ── helpers ──────────────────────────────────────────────────────────

    async def _backoff(self, attempt: int) -> None:
        if self.base_backoff_seconds <= 0:
            await self._sleep(0)
            return
        delay = min(
            self.max_backoff_seconds,
            self.base_backoff_seconds * (2**attempt),
        )
        if self.jitter > 0:
            factor = 1 - self.jitter + 2 * self.jitter * self._rng.random()
            delay = max(0.0, delay * factor)
        await self._sleep(delay)

    @staticmethod
    async def _sleep(seconds: float) -> None:
        await asyncio.sleep(seconds)


__all__ = [
    "Attempt",
    "Failover",
    "FailoverExhausted",
    "ProviderHTTPError",
    "ProviderTimeoutError",
]
