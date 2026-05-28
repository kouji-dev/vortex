"""Event writer + in-process pub/sub for live worker streams.

Writes events to ``worker_events`` (best-effort, async batched) and broadcasts
to in-process subscribers (the SSE endpoint) so the browser sees live events
without polling the DB.

Architecture:

- ``EventWriter`` is a process-wide singleton (per-process broadcast bus).
- ``emit()`` enqueues for DB persist AND publishes to subscribers immediately.
- A background ``_drain_loop`` flushes the queue in batches.
- ``subscribe(run_id, cb)`` registers an async callback; ``unsubscribe`` removes
  it. Subscribers receive ``EventRecord`` dataclasses (no ORM dependency).

The writer is intentionally decoupled from any specific SQLAlchemy session
factory — callers inject a ``session_factory`` (async context manager that
yields a session) on construction. Tests pass a no-op factory.
"""

from __future__ import annotations

import asyncio
import logging
import uuid as _uuid
from collections import defaultdict
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from ai_portal.workers.types import EventKind

log = logging.getLogger(__name__)

Subscriber = Callable[["EventRecord"], Awaitable[None]]


@dataclass(frozen=True)
class EventRecord:
    """Immutable event record broadcast to subscribers."""

    id: str
    run_id: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventWriter:
    """In-process event bus + batched persistence.

    Two responsibilities:

    1. **Broadcast** — every ``emit`` immediately invokes every subscriber
       for that run_id; failures are logged, never raised.
    2. **Persist** — events are queued and flushed in batches via the
       optional ``session_factory``. If ``None`` the persistence is skipped
       (test mode).
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], "asyncio.AbstractContextManager"] | None = None,
        flush_interval_sec: float = 0.25,
        max_batch: int = 200,
    ) -> None:
        self._subs: dict[str, list[Subscriber]] = defaultdict(list)
        self._queue: asyncio.Queue[EventRecord] = asyncio.Queue()
        self._session_factory = session_factory
        self._flush_interval = flush_interval_sec
        self._max_batch = max_batch
        self._task: asyncio.Task | None = None
        self._stopped = False

    # ── lifecycle ───────────────────────────────────────────────

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stopped = False
        self._task = asyncio.create_task(self._drain_loop())

    async def stop(self) -> None:
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    # ── subscribe / unsubscribe ─────────────────────────────────

    def subscribe(self, run_id: str, cb: Subscriber) -> None:
        self._subs[run_id].append(cb)

    def unsubscribe(self, run_id: str, cb: Subscriber) -> None:
        if cb in self._subs.get(run_id, []):
            self._subs[run_id].remove(cb)

    def subscriber_count(self, run_id: str) -> int:
        return len(self._subs.get(run_id, []))

    # ── emit ────────────────────────────────────────────────────

    async def emit(
        self, run_id: str, kind: EventKind | str, payload: dict[str, Any] | None = None
    ) -> EventRecord:
        """Publish to subscribers + enqueue for persist. Returns the record."""
        rec = EventRecord(
            id=_uuid.uuid4().hex,
            run_id=str(run_id),
            kind=kind.value if isinstance(kind, EventKind) else str(kind),
            payload=payload or {},
        )
        # broadcast first — fast, in-memory
        for cb in list(self._subs.get(rec.run_id, [])):
            try:
                await cb(rec)
            except Exception as e:  # noqa: BLE001
                log.warning("event subscriber failed: %s", e)
        # enqueue for DB persist (best-effort)
        await self._queue.put(rec)
        return rec

    # ── flush ───────────────────────────────────────────────────

    async def _drain_loop(self) -> None:
        while not self._stopped:
            try:
                first = await asyncio.wait_for(
                    self._queue.get(), timeout=self._flush_interval
                )
            except asyncio.TimeoutError:
                continue
            batch: list[EventRecord] = [first]
            while not self._queue.empty() and len(batch) < self._max_batch:
                batch.append(self._queue.get_nowait())
            await self._persist_batch(batch)

    async def _persist_batch(self, batch: list[EventRecord]) -> None:
        if not self._session_factory or not batch:
            return
        try:
            from ai_portal.workers.model import WorkerEvent as WE  # noqa: PLC0415

            async with self._session_factory() as session:  # type: ignore[misc]
                for rec in batch:
                    session.add(
                        WE(
                            id=_uuid.UUID(rec.id),
                            run_id=_uuid.UUID(rec.run_id),
                            kind=rec.kind,
                            payload_json=rec.payload,
                            ts=rec.ts,
                        )
                    )
                await session.flush()  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
            log.warning("event persist batch failed (n=%d): %s", len(batch), e)


# ── singleton accessor ─────────────────────────────────────────

_WRITER: EventWriter | None = None


def get_writer() -> EventWriter:
    """Process-wide writer singleton."""
    global _WRITER
    if _WRITER is None:
        _WRITER = EventWriter()
    return _WRITER


def set_writer(writer: EventWriter | None) -> None:
    """Override the singleton (tests)."""
    global _WRITER
    _WRITER = writer


@asynccontextmanager
async def subscription(writer: EventWriter, run_id: str, cb: Subscriber):
    """Context manager — ``subscribe`` on enter, ``unsubscribe`` on exit."""
    writer.subscribe(run_id, cb)
    try:
        yield
    finally:
        writer.unsubscribe(run_id, cb)
