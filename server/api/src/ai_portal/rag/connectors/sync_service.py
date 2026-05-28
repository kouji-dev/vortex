"""Sync orchestrator — drives a connector through one sync cycle.

Responsibilities:

1. Start a ``kb_sync_runs`` row (status=running).
2. Iterate ``connector.discover(cursor)``; for each :class:`SourceDoc`
   call ``enqueue_ingest(sd)`` which is expected to create an ingest job
   in the pipeline.
3. Per-doc errors are captured into ``kb_sync_errors`` and the run is
   marked ``partial``. A failure of ``discover`` itself flips the run to
   ``failed`` and stops iteration.
4. On success or partial, persist the connector's new ``delta_cursor()``
   back onto the row + ``kb_connectors.last_cursor``.

The repo is an opaque dependency — production wires it to a SQLAlchemy
implementation, tests pass an in-memory fake.

Scheduler is intentionally thin: a single asyncio task that polls the
connector table for due rows. Production would replace this with the
shared workers package; for v1 we ship the minimal driver.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable, Protocol

from ai_portal.rag.connectors.protocol import SourceDoc

log = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Outcome surfaced to the caller for tests / API responses."""

    status: str
    docs_added: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)
    cursor_after: str | None = None
    discover_error: str | None = None


class _Repo(Protocol):
    async def start_run(self, connector_id: Any) -> Any: ...

    async def end_run(
        self, run_id: Any, *, status: str, cursor_after: str | None
    ) -> None: ...

    async def increment(
        self,
        run_id: Any,
        *,
        added: int = 0,
        updated: int = 0,
        errors: int = 0,
    ) -> None: ...

    async def record_error(
        self, run_id: Any, source_uri: str, error: str
    ) -> None: ...

    async def update_connector_cursor(
        self, connector_id: Any, cursor: str | None, last_sync_at: datetime
    ) -> None: ...


EnqueueIngest = Callable[[SourceDoc], Any]


class SyncOrchestrator:
    """Drives one connector through one ``discover`` pass."""

    def __init__(
        self,
        *,
        repo: _Repo,
        enqueue_ingest: EnqueueIngest,
    ) -> None:
        self._repo = repo
        self._enqueue = enqueue_ingest

    async def run(
        self,
        *,
        connector_id: Any,
        connector: Any,
        cursor: str | None = None,
    ) -> SyncResult:
        run_id = await self._repo.start_run(connector_id)
        result = SyncResult(status="running")
        try:
            async for sd in connector.discover(cursor):
                try:
                    res = self._enqueue(sd)
                    if asyncio.iscoroutine(res):
                        await res
                    await self._repo.increment(run_id, added=1)
                    result.docs_added += 1
                except Exception as exc:  # per-doc isolation
                    await self._repo.increment(run_id, errors=1)
                    await self._repo.record_error(
                        run_id, sd.source_uri, str(exc)
                    )
                    result.errors.append((sd.source_uri, str(exc)))
                    log.warning(
                        "sync: per-doc failure", extra={
                            "connector_id": connector_id,
                            "source_uri": sd.source_uri,
                            "error": str(exc),
                        }
                    )
        except Exception as exc:
            result.discover_error = str(exc)
            await self._repo.end_run(
                run_id, status="failed", cursor_after=None
            )
            result.status = "failed"
            log.exception("sync: discover failed")
            return result

        cursor_after: str | None = None
        try:
            cursor_after = await connector.delta_cursor()
        except Exception:  # cursor is best-effort
            log.exception("sync: delta_cursor failed (ignored)")
        status = "partial" if result.errors else "success"
        await self._repo.end_run(
            run_id, status=status, cursor_after=cursor_after
        )
        await self._repo.update_connector_cursor(
            connector_id, cursor_after, datetime.now(UTC)
        )
        result.status = status
        result.cursor_after = cursor_after
        return result


# ----------------------------------------------------------------- scheduler --


class _DueProvider(Protocol):
    async def list_due(
        self, now: datetime
    ) -> list[tuple[Any, Any, str | None]]: ...
    """Return (connector_id, connector_instance, cursor) for each due row."""


class SyncScheduler:
    """Minimal asyncio polling loop.

    On each tick, asks the ``due_provider`` for connectors whose cron
    schedule fires before ``now`` and dispatches one orchestrator run
    per connector. Concurrent runs across connectors are allowed; per
    connector, a single in-flight run is enforced via a lock map.
    """

    def __init__(
        self,
        *,
        orchestrator: SyncOrchestrator,
        due_provider: _DueProvider,
        tick_seconds: float = 30.0,
    ) -> None:
        self._orchestrator = orchestrator
        self._due_provider = due_provider
        self._tick = tick_seconds
        self._locks: dict[Any, asyncio.Lock] = {}
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:  # pragma: no cover - infinite loop
        while not self._stop.is_set():
            await self._tick_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick)
            except asyncio.TimeoutError:
                continue

    async def _tick_once(self) -> None:
        now = datetime.now(UTC)
        try:
            due = await self._due_provider.list_due(now)
        except Exception:
            log.exception("sync scheduler: list_due failed")
            return
        for connector_id, connector, cursor in due:
            lock = self._locks.setdefault(connector_id, asyncio.Lock())
            if lock.locked():
                continue
            asyncio.create_task(
                self._run_one(connector_id, connector, cursor, lock)
            )

    async def _run_one(
        self,
        connector_id: Any,
        connector: Any,
        cursor: str | None,
        lock: asyncio.Lock,
    ) -> None:
        async with lock:
            try:
                await self._orchestrator.run(
                    connector_id=connector_id,
                    connector=connector,
                    cursor=cursor,
                )
            except Exception:
                log.exception(
                    "sync scheduler: run failed",
                    extra={"connector_id": connector_id},
                )
