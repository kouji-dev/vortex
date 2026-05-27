"""Webhook delivery worker — asyncio task + exponential backoff.

Two responsibilities:

1. :func:`compute_backoff` — pure function deciding ``next_attempt_at`` after
   a failed attempt. Schedule: 30s, 2m, 10m, 1h, 6h, then capped at 24h.

2. :class:`DeliveryWorker` — long-running asyncio task that polls
   ``webhook_deliveries`` for due rows, POSTs the payload signed with the
   webhook secret, then either marks ``delivered`` (2xx) or schedules a retry.

The worker is intentionally split from the HTTP send (``deliver_once``) so
tests can drive retries via :func:`respx` without spinning up the polling
loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid as _uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from ai_portal.webhooks.signer import sign_payload

logger = logging.getLogger(__name__)


# ── Backoff schedule ─────────────────────────────────────────────────────────

# Attempts: 1 → after 30s, 2 → +2m, 3 → +10m, 4 → +1h, 5 → +6h, ≥6 → +24h cap.
_BACKOFF_SECONDS: tuple[int, ...] = (
    30,          # after 1st failure
    2 * 60,      # after 2nd failure
    10 * 60,     # after 3rd failure
    60 * 60,     # after 4th failure
    6 * 60 * 60, # after 5th failure
)
_MAX_BACKOFF_SECONDS: int = 24 * 60 * 60   # 24h cap


def compute_backoff(attempts: int) -> timedelta:
    """Return delay to the next attempt after ``attempts`` failed tries.

    Schedule (caller calls with ``attempts`` = count after the failure):
    - attempts=1 → 30s
    - attempts=2 → 2m
    - attempts=3 → 10m
    - attempts=4 → 1h
    - attempts=5 → 6h
    - attempts ≥6 → capped at 24h
    """
    if attempts < 1:
        raise ValueError("attempts must be ≥ 1")
    idx = attempts - 1
    if idx < len(_BACKOFF_SECONDS):
        seconds = _BACKOFF_SECONDS[idx]
    else:
        seconds = _MAX_BACKOFF_SECONDS
    return timedelta(seconds=seconds)


def next_attempt_at(attempts: int, *, now: datetime | None = None) -> datetime:
    """``now + compute_backoff(attempts)`` — convenience for service callers."""
    now = now or datetime.now(UTC)
    return now + compute_backoff(attempts)


# ── In-memory delivery state for tests + dispatch result type ────────────────

@dataclass(slots=True)
class DeliveryResult:
    """Outcome of one delivery attempt.

    ``ok`` is True only for 2xx response. Otherwise the worker schedules a
    retry per :func:`compute_backoff` until ``attempts`` cap.
    """

    ok: bool
    status_code: int | None
    body: str | None
    error: str | None


# Max attempts before marking delivery permanently failed. Aligns with the
# 24h cap: 5 retries land at ~7h cumulative, two more 24h cycles ≈ 2 days
# of attempts before giving up.
MAX_ATTEMPTS = 8


# ── HTTP delivery ────────────────────────────────────────────────────────────

async def deliver_once(
    *,
    url: str,
    secret: bytes,
    event_id: _uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    timeout: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> DeliveryResult:
    """POST signed payload to ``url``. Returns DeliveryResult (does not raise).

    Body is canonical JSON (``sort_keys=True``). Signature header:
    ``X-Webhook-Signature: v1=<hex>``. ``X-Webhook-Event-Id`` / ``-Type``
    headers carry envelope metadata for the consumer.
    """
    body_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = sign_payload(body_bytes, secret)
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": sig,
        "X-Webhook-Event-Id": str(event_id),
        "X-Webhook-Event-Type": event_type,
    }

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=timeout)
    try:
        try:
            resp = await client.post(url, content=body_bytes, headers=headers)
        except httpx.HTTPError as e:
            return DeliveryResult(
                ok=False, status_code=None, body=None, error=str(e)[:512]
            )
        body_text = (resp.text or "")[:8192]
        return DeliveryResult(
            ok=200 <= resp.status_code < 300,
            status_code=resp.status_code,
            body=body_text,
            error=None,
        )
    finally:
        if owns_client:
            await client.aclose()


# ── Delivery worker ──────────────────────────────────────────────────────────

@dataclass(slots=True)
class _PendingDelivery:
    """Row-like value passed from store → worker."""

    id: _uuid.UUID
    webhook_id: _uuid.UUID
    org_id: _uuid.UUID
    event_id: _uuid.UUID
    event_type: str
    payload: dict[str, Any]
    url: str
    secret: bytes
    attempts: int


# Type aliases: the worker is DB-agnostic for testability. The service layer
# supplies thin closures over the SQLAlchemy session.
FetchDueFn = Callable[[datetime], Awaitable[list[_PendingDelivery]]]
RecordSuccessFn = Callable[[_uuid.UUID, DeliveryResult], Awaitable[None]]
RecordFailureFn = Callable[
    [_uuid.UUID, DeliveryResult, datetime | None, bool], Awaitable[None]
]


class DeliveryWorker:
    """Long-running asyncio task that drains due ``webhook_deliveries`` rows.

    Pull loop:
        while not stopped:
            rows = await fetch_due(now)
            for row in rows:
                result = await deliver_once(...)
                if result.ok:
                    await record_success(row.id, result)
                else:
                    next_at = compute next_attempt_at OR None if at cap
                    await record_failure(row.id, result, next_at, permanent)
            await asyncio.sleep(poll_interval)
    """

    def __init__(
        self,
        *,
        fetch_due: FetchDueFn,
        record_success: RecordSuccessFn,
        record_failure: RecordFailureFn,
        poll_interval: float = 5.0,
        max_attempts: int = MAX_ATTEMPTS,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._fetch_due = fetch_due
        self._record_success = record_success
        self._record_failure = record_failure
        self._poll_interval = poll_interval
        self._max_attempts = max_attempts
        self._client = http_client
        self._stop = asyncio.Event()

    async def run_once(self, *, now: datetime | None = None) -> int:
        """Drain a single batch of due deliveries. Returns row count handled."""
        now = now or datetime.now(UTC)
        rows = await self._fetch_due(now)
        for row in rows:
            await self._attempt(row, now)
        return len(rows)

    async def _attempt(self, row: _PendingDelivery, now: datetime) -> None:
        result = await deliver_once(
            url=row.url,
            secret=row.secret,
            event_id=row.event_id,
            event_type=row.event_type,
            payload=row.payload,
            client=self._client,
        )
        if result.ok:
            await self._record_success(row.id, result)
            return

        # Failure → schedule retry or give up.
        attempts_after = row.attempts + 1
        if attempts_after >= self._max_attempts:
            await self._record_failure(row.id, result, None, True)
            logger.warning(
                "webhook delivery permanently failed delivery_id=%s attempts=%d",
                row.id,
                attempts_after,
            )
            return
        retry_at = now + compute_backoff(attempts_after)
        await self._record_failure(row.id, result, retry_at, False)

    async def run_forever(self) -> None:  # pragma: no cover — integration loop
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("webhook delivery worker tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll_interval)
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()
