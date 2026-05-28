"""Brute-force limiter — sliding window per (ip, email).

Phase M3 of the Control Plane plan. In-process for now; swap the backing store
to Redis once a shared deployment lands.

Contract:

- ``record_failure(ip, email)`` adds a timestamp to the bucket.
- ``record_success(ip, email)`` clears the bucket (legit login resets).
- ``check(ip, email)`` returns ``None`` if allowed, or the number of seconds
  until the oldest attempt in the window expires (use as Retry-After).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Iterable

LIMIT_FAILED_ATTEMPTS = 10
WINDOW_SECONDS = 60


class LoginLimiter:
    """Thread-safe sliding-window failure counter."""

    def __init__(
        self,
        *,
        limit: int = LIMIT_FAILED_ATTEMPTS,
        window_seconds: int = WINDOW_SECONDS,
        clock=time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    # ── public ───────────────────────────────────────────────────────────────

    def check(self, ip: str, email: str) -> int | None:
        """Return seconds-until-retry if blocked, else None."""
        key = self._key(ip, email)
        now = self._clock()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return None
            self._evict(bucket, now)
            if len(bucket) >= self._limit:
                oldest = bucket[0]
                retry_in = int(self._window - (now - oldest))
                return max(retry_in, 1)
            return None

    def record_failure(self, ip: str, email: str) -> None:
        key = self._key(ip, email)
        now = self._clock()
        with self._lock:
            bucket = self._buckets[key]
            self._evict(bucket, now)
            bucket.append(now)

    def record_success(self, ip: str, email: str) -> None:
        key = self._key(ip, email)
        with self._lock:
            self._buckets.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._buckets.clear()

    # ── internals ────────────────────────────────────────────────────────────

    @staticmethod
    def _key(ip: str, email: str) -> tuple[str, str]:
        return (ip or "-", (email or "").lower().strip())

    def _evict(self, bucket: Iterable[float], now: float) -> None:
        # bucket is a deque; mutate in place.
        b: deque[float] = bucket  # type: ignore[assignment]
        while b and now - b[0] > self._window:
            b.popleft()


# Module-level singleton — fine because the FastAPI worker process is sticky
# per failure-IP. Swap for a Redis-backed impl when we deploy multi-worker.
login_limiter = LoginLimiter()
