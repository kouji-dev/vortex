"""Token-bucket backends for gateway rate limits.

Two backends, picked at runtime:

- :class:`RedisBucket`     — production. Atomic via Lua, shared across
  processes.
- :class:`InMemoryBucket`  — single-process fallback (tests / dev /
  Redis-unavailable). State lives in a module-level dict keyed by bucket
  name; trivially racy across processes but deterministic in a single one.

Public surface:

- :class:`TokenBucket` — Protocol with ``consume(key, capacity, refill_rate,
  tokens, now)`` and ``peek(key, capacity, refill_rate, now)``.
- :class:`ConsumeResult` — return shape ``(allowed, remaining, retry_after)``.
- :func:`build_bucket(redis_url=None) -> TokenBucket` — factory.

Bucket semantics:

- Each ``key`` owns a *level* (float) and a *last-refill timestamp*.
- ``capacity``     = max tokens the bucket can hold (limit + burst).
- ``refill_rate``  = tokens added per second.
- ``consume(tokens)`` refills based on elapsed seconds, then subtracts.
  - If ``level >= tokens`` → allowed, ``remaining = floor(level - tokens)``,
    ``retry_after = 0``.
  - Else                   → denied, ``remaining = floor(level)``,
    ``retry_after = ceil((tokens - level) / refill_rate)``.

For ``concurrent_requests`` the caller passes ``refill_rate=0`` and uses
:meth:`release` after the call completes.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ConsumeResult:
    allowed: bool
    remaining: int
    retry_after: int  # seconds; 0 when allowed


class TokenBucket(Protocol):
    """Backend-agnostic token-bucket interface."""

    def consume(
        self,
        key: str,
        *,
        capacity: float,
        refill_per_second: float,
        tokens: float = 1.0,
        now: float | None = None,
    ) -> ConsumeResult: ...

    def peek(
        self,
        key: str,
        *,
        capacity: float,
        refill_per_second: float,
        now: float | None = None,
    ) -> float:
        """Return the current level after refill, without consuming."""
        ...

    def release(self, key: str, *, tokens: float = 1.0) -> None:
        """Return tokens (concurrent_requests dimension)."""
        ...

    def reset(self, key: str | None = None) -> None:
        """Clear a single bucket or, if ``key`` is None, every bucket."""
        ...


# ── in-memory backend ───────────────────────────────────────────────────────


_state: dict[str, tuple[float, float]] = {}  # key -> (level, last_ts)
_lock = threading.Lock()


class InMemoryBucket:
    """Process-local token bucket. Use for dev / tests / single-worker only."""

    def __init__(self) -> None:
        # Stateless instance; state lives in module-level dict so multiple
        # callers in the same process share the same bucket regardless of
        # who constructed the wrapper.
        pass

    def _refill(
        self, key: str, capacity: float, refill_per_second: float, now: float
    ) -> float:
        """Return the bucket level after refilling. Updates state."""
        level, last_ts = _state.get(key, (capacity, now))
        if refill_per_second > 0:
            elapsed = max(0.0, now - last_ts)
            level = min(capacity, level + elapsed * refill_per_second)
        _state[key] = (level, now)
        return level

    def consume(
        self,
        key: str,
        *,
        capacity: float,
        refill_per_second: float,
        tokens: float = 1.0,
        now: float | None = None,
    ) -> ConsumeResult:
        ts = time.monotonic() if now is None else now
        with _lock:
            level = self._refill(key, capacity, refill_per_second, ts)
            if level >= tokens:
                level -= tokens
                _state[key] = (level, ts)
                return ConsumeResult(
                    allowed=True, remaining=int(math.floor(level)), retry_after=0
                )
            # Denied — restore level (we didn't subtract).
            deficit = tokens - level
            retry_after = (
                int(math.ceil(deficit / refill_per_second))
                if refill_per_second > 0
                else 1
            )
            # ensure retry_after >= 1 to avoid clients hammering instantly.
            retry_after = max(1, retry_after)
            return ConsumeResult(
                allowed=False,
                remaining=int(math.floor(level)),
                retry_after=retry_after,
            )

    def peek(
        self,
        key: str,
        *,
        capacity: float,
        refill_per_second: float,
        now: float | None = None,
    ) -> float:
        ts = time.monotonic() if now is None else now
        with _lock:
            return self._refill(key, capacity, refill_per_second, ts)

    def release(self, key: str, *, tokens: float = 1.0) -> None:
        """Add ``tokens`` back; cap at the bucket's last-known capacity.

        ``concurrent_requests`` buckets call this when the request finishes.
        We can't enforce a cap without knowing capacity, so callers should
        wrap this with a known max via :meth:`reset_to` if needed.
        """
        with _lock:
            level, last_ts = _state.get(key, (tokens, time.monotonic()))
            _state[key] = (level + tokens, last_ts)

    def reset(self, key: str | None = None) -> None:
        with _lock:
            if key is None:
                _state.clear()
                return
            _state.pop(key, None)


# ── redis backend ───────────────────────────────────────────────────────────


_REDIS_CONSUME_LUA = """
-- KEYS[1] = bucket key
-- ARGV    = capacity, refill_per_second, tokens, now_ms
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local tokens = tonumber(ARGV[3])
local now_ms = tonumber(ARGV[4])

local data = redis.call('HMGET', KEYS[1], 'level', 'ts')
local level = tonumber(data[1])
local ts = tonumber(data[2])
if level == nil then
  level = capacity
  ts = now_ms
end
local elapsed = math.max(0, (now_ms - ts) / 1000.0)
if rate > 0 then
  level = math.min(capacity, level + elapsed * rate)
end
local allowed = 0
local retry_after = 0
if level >= tokens then
  level = level - tokens
  allowed = 1
else
  local deficit = tokens - level
  if rate > 0 then
    retry_after = math.ceil(deficit / rate)
  else
    retry_after = 1
  end
  if retry_after < 1 then retry_after = 1 end
end
redis.call('HMSET', KEYS[1], 'level', tostring(level), 'ts', tostring(now_ms))
-- give buckets a generous TTL so abandoned scopes don't accumulate forever.
redis.call('EXPIRE', KEYS[1], 86400)
return {allowed, math.floor(level), retry_after}
"""


class RedisBucket:
    """Production token bucket — atomic via server-side Lua."""

    def __init__(self, redis_client) -> None:  # noqa: ANN001 (duck-typed)
        self._r = redis_client
        try:
            self._script = self._r.register_script(_REDIS_CONSUME_LUA)
        except Exception:  # pragma: no cover — defer to first call
            self._script = None

    def consume(
        self,
        key: str,
        *,
        capacity: float,
        refill_per_second: float,
        tokens: float = 1.0,
        now: float | None = None,
    ) -> ConsumeResult:
        now_ms = int((time.time() if now is None else now) * 1000)
        if self._script is None:
            self._script = self._r.register_script(_REDIS_CONSUME_LUA)
        res = self._script(
            keys=[key],
            args=[capacity, refill_per_second, tokens, now_ms],
        )
        allowed, remaining, retry_after = res
        return ConsumeResult(
            allowed=bool(allowed),
            remaining=int(remaining),
            retry_after=int(retry_after),
        )

    def peek(
        self,
        key: str,
        *,
        capacity: float,
        refill_per_second: float,
        now: float | None = None,
    ) -> float:
        data = self._r.hmget(key, "level", "ts")
        if data[0] is None:
            return float(capacity)
        level = float(data[0])
        ts_ms = float(data[1] or 0)
        now_ms = (time.time() if now is None else now) * 1000
        elapsed = max(0.0, (now_ms - ts_ms) / 1000.0)
        if refill_per_second > 0:
            level = min(capacity, level + elapsed * refill_per_second)
        return level

    def release(self, key: str, *, tokens: float = 1.0) -> None:
        # Best-effort; capacity unknown server-side. Use HINCRBYFLOAT.
        try:
            self._r.hincrbyfloat(key, "level", tokens)
        except Exception:  # pragma: no cover
            pass

    def reset(self, key: str | None = None) -> None:
        if key is None:
            # Don't FLUSHDB — caller probably shares Redis. Skip.
            return
        self._r.delete(key)


def build_bucket(redis_url: str | None = None) -> TokenBucket:
    """Construct a bucket backend. Redis if URL given + connectable, else memory."""
    if redis_url:
        try:  # pragma: no cover — exercised in prod
            import redis  # type: ignore

            client = redis.from_url(redis_url, decode_responses=True)
            client.ping()
            return RedisBucket(client)
        except Exception:
            pass
    return InMemoryBucket()
