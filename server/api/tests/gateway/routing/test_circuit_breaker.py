"""C2: circuit breaker state machine.

Three states: ``closed`` (normal), ``open`` (deny without trying), and
``half_open`` (one probe in flight). The breaker opens after N consecutive
failures, stays open for ``recovery_seconds``, then admits a single probe;
success closes, failure re-opens.
"""

from __future__ import annotations

import pytest

from ai_portal.gateway.routing.circuit_breaker import (
    CircuitBreaker,
    CircuitOpen,
    CircuitState,
)


def test_breaker_starts_closed():
    cb = CircuitBreaker(failure_threshold=3, recovery_seconds=10)
    assert cb.state("k") is CircuitState.CLOSED
    cb.allow("k")  # no raise


def test_breaker_opens_after_threshold_consecutive_failures():
    cb = CircuitBreaker(failure_threshold=3, recovery_seconds=10, now=lambda: 0.0)
    for _ in range(3):
        cb.record_failure("k")
    assert cb.state("k") is CircuitState.OPEN


def test_open_breaker_denies_allow_calls():
    cb = CircuitBreaker(failure_threshold=2, recovery_seconds=60, now=lambda: 0.0)
    cb.record_failure("k")
    cb.record_failure("k")
    with pytest.raises(CircuitOpen):
        cb.allow("k")


def test_success_resets_failure_count():
    cb = CircuitBreaker(failure_threshold=3, recovery_seconds=60, now=lambda: 0.0)
    cb.record_failure("k")
    cb.record_failure("k")
    cb.record_success("k")
    cb.record_failure("k")
    cb.record_failure("k")
    # Only 2 consecutive failures since last success → still closed.
    assert cb.state("k") is CircuitState.CLOSED


def test_recovery_window_transitions_to_half_open():
    clock = [0.0]
    cb = CircuitBreaker(failure_threshold=2, recovery_seconds=10, now=lambda: clock[0])
    cb.record_failure("k")
    cb.record_failure("k")
    assert cb.state("k") is CircuitState.OPEN

    # Inside the recovery window — still open.
    clock[0] = 5.0
    assert cb.state("k") is CircuitState.OPEN

    # Past the recovery window — half-open: one probe allowed.
    clock[0] = 11.0
    assert cb.state("k") is CircuitState.HALF_OPEN
    cb.allow("k")  # probe in flight; allowed once
    # Second probe in the same half-open window denied.
    with pytest.raises(CircuitOpen):
        cb.allow("k")


def test_half_open_success_closes_breaker():
    clock = [0.0]
    cb = CircuitBreaker(failure_threshold=2, recovery_seconds=10, now=lambda: clock[0])
    cb.record_failure("k")
    cb.record_failure("k")
    clock[0] = 20.0
    cb.allow("k")
    cb.record_success("k")
    assert cb.state("k") is CircuitState.CLOSED


def test_half_open_failure_reopens_breaker():
    clock = [0.0]
    cb = CircuitBreaker(failure_threshold=2, recovery_seconds=10, now=lambda: clock[0])
    cb.record_failure("k")
    cb.record_failure("k")
    clock[0] = 20.0
    cb.allow("k")  # probe
    cb.record_failure("k")  # probe failed
    assert cb.state("k") is CircuitState.OPEN
    # Window resets — opened at t=20.
    clock[0] = 25.0
    with pytest.raises(CircuitOpen):
        cb.allow("k")


def test_keys_are_independent():
    cb = CircuitBreaker(failure_threshold=2, recovery_seconds=10, now=lambda: 0.0)
    cb.record_failure("a")
    cb.record_failure("a")
    cb.record_failure("b")
    assert cb.state("a") is CircuitState.OPEN
    assert cb.state("b") is CircuitState.CLOSED
