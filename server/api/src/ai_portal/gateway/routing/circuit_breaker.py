"""Per-key circuit breaker for the gateway routing layer.

A *key* is typically ``f"{provider}:{model_id}"`` so the breaker tracks
each concrete provider-model pair independently. State machine:

- ``closed``     — normal traffic
- ``open``       — denies all attempts until ``recovery_seconds`` elapses
- ``half_open``  — admits exactly one probe; success → ``closed``,
  failure → ``open`` with the recovery clock reset

The breaker is *consecutive-failure based* — a single success resets the
counter. Time is injected via the ``now`` callable so tests pin it.
"""

from __future__ import annotations

import enum
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field


class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpen(Exception):
    """Raised by :meth:`CircuitBreaker.allow` when the circuit denies."""

    def __init__(self, key: str) -> None:
        super().__init__(f"circuit open for {key}")
        self.key = key


@dataclass
class _Slot:
    failures: int = 0
    opened_at: float | None = None
    half_open_probe_in_flight: bool = False
    last_failure_at: float = 0.0


@dataclass
class CircuitBreaker:
    """Per-key circuit breaker.

    Thread-safe — uses an internal lock since :meth:`allow` /
    :meth:`record_failure` may race when a request is processing failover
    on one thread while telemetry is updating from another.
    """

    failure_threshold: int = 5
    recovery_seconds: float = 30.0
    now: Callable[[], float] = field(default_factory=lambda: time.monotonic)
    _slots: dict[str, _Slot] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    # ── public ───────────────────────────────────────────────────────────

    def state(self, key: str) -> CircuitState:
        with self._lock:
            return self._state_locked(key)

    def allow(self, key: str) -> None:
        """Raise :class:`CircuitOpen` if the circuit denies; else admit one."""
        with self._lock:
            st = self._state_locked(key)
            if st is CircuitState.OPEN:
                raise CircuitOpen(key)
            if st is CircuitState.HALF_OPEN:
                slot = self._slots[key]
                if slot.half_open_probe_in_flight:
                    raise CircuitOpen(key)
                slot.half_open_probe_in_flight = True

    def record_success(self, key: str) -> None:
        with self._lock:
            slot = self._slots.get(key)
            if slot is None:
                return
            slot.failures = 0
            slot.opened_at = None
            slot.half_open_probe_in_flight = False

    def record_failure(self, key: str) -> None:
        with self._lock:
            slot = self._slots.setdefault(key, _Slot())
            slot.failures += 1
            slot.last_failure_at = self.now()
            slot.half_open_probe_in_flight = False
            if slot.failures >= self.failure_threshold:
                slot.opened_at = self.now()

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._slots.clear()
            else:
                self._slots.pop(key, None)

    # ── internals ────────────────────────────────────────────────────────

    def _state_locked(self, key: str) -> CircuitState:
        slot = self._slots.get(key)
        if slot is None:
            return CircuitState.CLOSED
        if slot.opened_at is None:
            return CircuitState.CLOSED
        elapsed = self.now() - slot.opened_at
        if elapsed >= self.recovery_seconds:
            return CircuitState.HALF_OPEN
        return CircuitState.OPEN


__all__ = ["CircuitBreaker", "CircuitOpen", "CircuitState"]
