"""Webhook delivery worker — backoff schedule + retry behaviour via respx."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from ai_portal.webhooks.signer import sign_payload
from ai_portal.webhooks.worker import (
    MAX_ATTEMPTS,
    DeliveryResult,
    DeliveryWorker,
    _PendingDelivery,
    compute_backoff,
    deliver_once,
    next_attempt_at,
)

# ── Backoff schedule ─────────────────────────────────────────────────────────


def test_compute_backoff_schedule() -> None:
    assert compute_backoff(1) == timedelta(seconds=30)
    assert compute_backoff(2) == timedelta(minutes=2)
    assert compute_backoff(3) == timedelta(minutes=10)
    assert compute_backoff(4) == timedelta(hours=1)
    assert compute_backoff(5) == timedelta(hours=6)


def test_compute_backoff_caps_at_24h() -> None:
    for attempts in range(6, 50):
        assert compute_backoff(attempts) == timedelta(hours=24), attempts


def test_compute_backoff_rejects_zero() -> None:
    with pytest.raises(ValueError):
        compute_backoff(0)


def test_next_attempt_at_adds_delay() -> None:
    now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
    assert next_attempt_at(1, now=now) == now + timedelta(seconds=30)
    assert next_attempt_at(2, now=now) == now + timedelta(minutes=2)


# ── deliver_once: HTTP send + signing ────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_deliver_once_signs_and_returns_ok_on_2xx() -> None:
    route = respx.post("https://example.test/hook").mock(
        return_value=httpx.Response(200, text="ok")
    )
    event_id = uuid.uuid4()
    payload = {"a": 1, "b": "hi"}
    secret = b"shh"

    result = await deliver_once(
        url="https://example.test/hook",
        secret=secret,
        event_id=event_id,
        event_type="budget.exceeded",
        payload=payload,
    )

    assert result.ok is True
    assert result.status_code == 200
    assert result.body == "ok"
    assert route.called

    req = route.calls[0].request
    # Body is canonical JSON
    body_bytes = bytes(req.content)
    assert body_bytes == json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    # Signature header is valid against the body
    sig = req.headers["X-Webhook-Signature"]
    assert sig == sign_payload(body_bytes, secret)
    assert req.headers["X-Webhook-Event-Id"] == str(event_id)
    assert req.headers["X-Webhook-Event-Type"] == "budget.exceeded"


@pytest.mark.asyncio
@respx.mock
async def test_deliver_once_marks_5xx_as_failure() -> None:
    respx.post("https://example.test/hook").mock(
        return_value=httpx.Response(503, text="upstream down")
    )
    result = await deliver_once(
        url="https://example.test/hook",
        secret=b"k",
        event_id=uuid.uuid4(),
        event_type="t",
        payload={},
    )
    assert result.ok is False
    assert result.status_code == 503
    assert result.body == "upstream down"


@pytest.mark.asyncio
@respx.mock
async def test_deliver_once_marks_4xx_as_failure() -> None:
    respx.post("https://example.test/hook").mock(
        return_value=httpx.Response(404, text="not found")
    )
    result = await deliver_once(
        url="https://example.test/hook",
        secret=b"k",
        event_id=uuid.uuid4(),
        event_type="t",
        payload={},
    )
    assert result.ok is False
    assert result.status_code == 404


@pytest.mark.asyncio
@respx.mock
async def test_deliver_once_captures_network_error() -> None:
    respx.post("https://example.test/hook").mock(
        side_effect=httpx.ConnectError("dns fail")
    )
    result = await deliver_once(
        url="https://example.test/hook",
        secret=b"k",
        event_id=uuid.uuid4(),
        event_type="t",
        payload={},
    )
    assert result.ok is False
    assert result.status_code is None
    assert "dns fail" in (result.error or "")


# ── DeliveryWorker.run_once ──────────────────────────────────────────────────


class _FakeStore:
    """In-memory replacement for the service layer."""

    def __init__(self) -> None:
        self.due: list[_PendingDelivery] = []
        self.successes: list[tuple[uuid.UUID, DeliveryResult]] = []
        self.failures: list[tuple[uuid.UUID, DeliveryResult, datetime | None, bool]] = []

    async def fetch_due(self, now: datetime) -> list[_PendingDelivery]:
        rows = self.due
        self.due = []
        return rows

    async def record_success(self, delivery_id: uuid.UUID, result: DeliveryResult) -> None:
        self.successes.append((delivery_id, result))

    async def record_failure(
        self,
        delivery_id: uuid.UUID,
        result: DeliveryResult,
        next_at: datetime | None,
        permanent: bool,
    ) -> None:
        self.failures.append((delivery_id, result, next_at, permanent))


def _make_row(*, attempts: int = 0, url: str = "https://hook.test/x") -> _PendingDelivery:
    return _PendingDelivery(
        id=uuid.uuid4(),
        webhook_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        event_type="budget.exceeded",
        payload={"hello": "world"},
        url=url,
        secret=b"shh",
        attempts=attempts,
    )


@pytest.mark.asyncio
@respx.mock
async def test_worker_records_success_on_2xx() -> None:
    respx.post("https://hook.test/x").mock(return_value=httpx.Response(200))
    store = _FakeStore()
    row = _make_row()
    store.due = [row]

    worker = DeliveryWorker(
        fetch_due=store.fetch_due,
        record_success=store.record_success,
        record_failure=store.record_failure,
    )
    n = await worker.run_once()

    assert n == 1
    assert len(store.successes) == 1
    assert store.successes[0][0] == row.id
    assert store.failures == []


@pytest.mark.asyncio
@respx.mock
async def test_worker_schedules_retry_at_30s_on_first_5xx() -> None:
    respx.post("https://hook.test/x").mock(return_value=httpx.Response(503))
    store = _FakeStore()
    row = _make_row(attempts=0)
    store.due = [row]

    worker = DeliveryWorker(
        fetch_due=store.fetch_due,
        record_success=store.record_success,
        record_failure=store.record_failure,
    )
    now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
    await worker.run_once(now=now)

    assert len(store.failures) == 1
    delivery_id, result, next_at, permanent = store.failures[0]
    assert delivery_id == row.id
    assert result.status_code == 503
    assert permanent is False
    assert next_at == now + timedelta(seconds=30)


@pytest.mark.asyncio
@respx.mock
async def test_worker_progresses_backoff_across_attempts() -> None:
    """5xx for rows with attempts=1,2,3 → retry at 2m, 10m, 1h."""
    respx.post("https://hook.test/x").mock(return_value=httpx.Response(500))
    store = _FakeStore()
    rows = [_make_row(attempts=a) for a in (1, 2, 3)]
    store.due = list(rows)

    worker = DeliveryWorker(
        fetch_due=store.fetch_due,
        record_success=store.record_success,
        record_failure=store.record_failure,
    )
    now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
    await worker.run_once(now=now)

    assert len(store.failures) == 3
    delays = [(fail[2] - now) for fail in store.failures]
    assert delays == [
        timedelta(minutes=2),
        timedelta(minutes=10),
        timedelta(hours=1),
    ]
    for _, _, _, permanent in store.failures:
        assert permanent is False


@pytest.mark.asyncio
@respx.mock
async def test_worker_caps_retry_at_24h() -> None:
    respx.post("https://hook.test/x").mock(return_value=httpx.Response(500))
    store = _FakeStore()
    # attempts=5 → after failure attempts_after=6 → 24h cap
    row = _make_row(attempts=5)
    store.due = [row]

    worker = DeliveryWorker(
        fetch_due=store.fetch_due,
        record_success=store.record_success,
        record_failure=store.record_failure,
    )
    now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
    await worker.run_once(now=now)

    assert len(store.failures) == 1
    _, _, next_at, permanent = store.failures[0]
    assert next_at == now + timedelta(hours=24)
    assert permanent is False


@pytest.mark.asyncio
@respx.mock
async def test_worker_marks_permanent_after_max_attempts() -> None:
    respx.post("https://hook.test/x").mock(return_value=httpx.Response(500))
    store = _FakeStore()
    # attempts = MAX_ATTEMPTS - 1 → +1 = MAX → permanent
    row = _make_row(attempts=MAX_ATTEMPTS - 1)
    store.due = [row]

    worker = DeliveryWorker(
        fetch_due=store.fetch_due,
        record_success=store.record_success,
        record_failure=store.record_failure,
    )
    await worker.run_once()

    assert len(store.failures) == 1
    _, _, next_at, permanent = store.failures[0]
    assert next_at is None
    assert permanent is True


@pytest.mark.asyncio
@respx.mock
async def test_worker_run_once_no_due_rows_returns_zero() -> None:
    store = _FakeStore()
    worker = DeliveryWorker(
        fetch_due=store.fetch_due,
        record_success=store.record_success,
        record_failure=store.record_failure,
    )
    assert await worker.run_once() == 0
    assert store.successes == []
    assert store.failures == []
