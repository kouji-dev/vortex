"""Async TraceWriter — buffers + flushes off the hot path.

Hot path calls ``writer.record(...)`` (or ``submit``) and returns immediately.
A background task drains the queue and flushes rows in batches.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TraceRecord:
    org_id: uuid.UUID
    route: str
    actor_json: dict[str, Any] = field(default_factory=dict)
    model_requested: str | None = None
    model_used: str | None = None
    provider: str | None = None
    status: str = "ok"
    latency_ms: int | None = None
    ttft_ms: int | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cache_read: int = 0
    tokens_cache_write: int = 0
    cost_cents: float = 0.0
    cache_hit: bool = False
    error: str | None = None
    request_hash: str | None = None
    request_json: dict[str, Any] | None = None
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: uuid.UUID = field(default_factory=uuid.uuid4)

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        # JSONB column is fine with dict; ids/datetimes pass through.
        return row


class TraceWriter:
    """Buffered async writer. Non-blocking ``submit``; flushed by drain task."""

    def __init__(self, batch_size: int = 50, flush_interval: float = 1.0) -> None:
        self._queue: asyncio.Queue[TraceRecord] = asyncio.Queue()
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    def submit(self, record: TraceRecord) -> None:
        """Non-blocking enqueue. Never raises on the hot path."""
        if self._closed:
            return
        try:
            self._queue.put_nowait(record)
        except Exception as exc:  # noqa: BLE001
            logger.warning("trace_submit_failed: %s", exc)

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._drain_loop())

    async def stop(self) -> None:
        self._closed = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        await self.flush()

    async def flush(self) -> int:
        """Drain queue and write all pending. Returns rows written."""
        batch: list[TraceRecord] = []
        while not self._queue.empty():
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if not batch:
            return 0
        return await self._flush_batch(batch)

    async def _drain_loop(self) -> None:
        while not self._closed:
            try:
                first = await asyncio.wait_for(
                    self._queue.get(), timeout=self._flush_interval
                )
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            batch: list[TraceRecord] = [first]
            while len(batch) < self._batch_size and not self._queue.empty():
                try:
                    batch.append(self._queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            try:
                await self._flush_batch(batch)
            except Exception as exc:  # noqa: BLE001
                logger.error("trace_flush_failed: %s", exc)

    async def _flush_batch(self, batch: list[TraceRecord]) -> int:
        # Run blocking DB write in a thread.
        return await asyncio.to_thread(_write_rows_sync, batch)


def _write_rows_sync(batch: list[TraceRecord]) -> int:
    """Synchronous bulk insert into request_traces. Bypasses RLS."""
    if not batch:
        return 0
    from ai_portal.core.db.rls import bypass_rls  # noqa: PLC0415
    from ai_portal.core.db.session import SessionLocal  # noqa: PLC0415
    from ai_portal.gateway.traces.model import RequestTrace  # noqa: PLC0415

    rows = [RequestTrace(**rec.to_row()) for rec in batch]
    try:
        with SessionLocal() as db:
            with bypass_rls(db):
                db.add_all(rows)
                db.commit()
        return len(rows)
    except Exception as exc:  # noqa: BLE001
        logger.error("trace_write_failed: %s", exc)
        return 0


_writer_singleton: TraceWriter | None = None


def get_writer() -> TraceWriter:
    """Process-wide singleton TraceWriter."""
    global _writer_singleton
    if _writer_singleton is None:
        _writer_singleton = TraceWriter()
    return _writer_singleton


def reset_writer() -> None:
    """Test hook — reset singleton."""
    global _writer_singleton
    _writer_singleton = None
