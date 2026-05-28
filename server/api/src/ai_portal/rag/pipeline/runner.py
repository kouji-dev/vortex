"""Pipeline runner — orchestrates the 8 ingest stages.

Design goals:

- **Per-doc failure isolation.** A stage exception quarantines the
  document being processed; other queued documents proceed.
- **Retry policy per stage.** Stages declare ``retries`` (default 0).
  Transient :class:`RetryableStageError` triggers exponential backoff
  before falling through to quarantine.
- **Progress + error hooks.** ``on_progress`` and ``on_error`` are
  optional callables; production wiring binds them to audit / webhooks /
  the in-DB ``kb_ingest_steps`` table.
- **Stage purity.** Each stage receives + returns a :class:`StageCtx`.
  The runner owns lifecycle bookkeeping (start/complete/fail) so stages
  stay focused on their transformation.

The runner deliberately keeps imports light. Concrete stage functions
live under :mod:`ai_portal.rag.pipeline.stages` and accept the same
context — they're wired by name through :attr:`PipelineDeps.stages` so
test code can substitute fakes for any subset.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import Any

from ai_portal.rag.chunkers.protocol import Chunk
from ai_portal.rag.extractors.protocol import ExtractedDocument

logger = logging.getLogger(__name__)

# ── public types ─────────────────────────────────────────────────────────


class Stage(str, Enum):
    fetch = "fetch"
    extract = "extract"
    normalize = "normalize"
    redact = "redact"
    chunk = "chunk"
    enrich = "enrich"
    embed = "embed"
    index = "index"


STAGES: tuple[Stage, ...] = (
    Stage.fetch,
    Stage.extract,
    Stage.normalize,
    Stage.redact,
    Stage.chunk,
    Stage.enrich,
    Stage.embed,
    Stage.index,
)


class StageError(RuntimeError):
    """Stage failed — document will be quarantined."""

    def __init__(self, stage: Stage, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(f"{stage.value}: {message}")
        self.stage = stage
        self.cause = cause


class RetryableStageError(StageError):
    """Transient — runner may retry per stage policy."""


@dataclass(slots=True)
class StageCtx:
    """Mutable context threaded through stages."""

    job_id: str
    document_id: str
    kb_id: str
    source_uri: str = ""
    mime: str = ""
    raw_bytes: bytes | None = None
    extracted: ExtractedDocument | None = None
    chunks: list[Chunk] = field(default_factory=list)
    embeddings: list[list[float]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    # Knowledge-base settings the stages reference (chunker_id, embedder_id, etc.).
    kb_settings: dict[str, Any] = field(default_factory=dict)


class StageOutcome(str, Enum):
    ok = "ok"
    retried = "retried"
    failed = "failed"


@dataclass(slots=True)
class StageResult:
    stage: Stage
    outcome: StageOutcome
    started_at: float
    ended_at: float
    error: str | None = None
    attempts: int = 1

    @property
    def latency_ms(self) -> int:
        return int((self.ended_at - self.started_at) * 1000)


@dataclass(slots=True)
class PipelineResult:
    job_id: str
    document_id: str
    success: bool
    stages: list[StageResult] = field(default_factory=list)
    quarantine_reason: str | None = None


# ── deps ─────────────────────────────────────────────────────────────────

StageFn = Callable[[StageCtx], Awaitable[StageCtx]]
ProgressHook = Callable[[StageCtx, Stage, StageOutcome, StageResult], Awaitable[None] | None]
ErrorHook = Callable[[StageCtx, Stage, BaseException], Awaitable[None] | None]


@dataclass(slots=True)
class PipelineDeps:
    """Injected stage implementations + observability hooks.

    ``stages`` is keyed by :class:`Stage`. Missing stages become no-ops
    so tests can spotlight a subset.
    """

    stages: dict[Stage, StageFn]
    retries: dict[Stage, int] = field(default_factory=dict)
    backoff_base: float = 0.0  # seconds; 0 keeps tests fast
    on_progress: ProgressHook | None = None
    on_error: ErrorHook | None = None
    quarantine_doc: Callable[[str, str], Awaitable[None] | None] | None = None
    mark_indexed: Callable[[str], Awaitable[None] | None] | None = None


# ── runner ───────────────────────────────────────────────────────────────


class PipelineRunner:
    """Runs the 8-stage pipeline for one document.

    Use :meth:`run` for a single doc, :meth:`run_many` to process a
    batch with per-doc isolation — one bad doc never blocks the others.
    """

    def __init__(self, deps: PipelineDeps) -> None:
        self.deps = deps

    async def run(self, ctx: StageCtx) -> PipelineResult:
        results: list[StageResult] = []
        for stage in STAGES:
            fn = self.deps.stages.get(stage)
            retries = self.deps.retries.get(stage, 0)
            attempts = 0
            started = monotonic()
            last_error: BaseException | None = None
            outcome = StageOutcome.ok
            while True:
                attempts += 1
                try:
                    if fn is not None:
                        ctx = await fn(ctx)
                    last_error = None
                    # success — keep outcome at the default `ok`.
                    outcome = StageOutcome.ok
                    break
                except RetryableStageError as exc:
                    last_error = exc
                    if attempts > retries:
                        outcome = StageOutcome.failed
                        break
                    # Will retry — leave a transient marker for observers.
                    await self._sleep_backoff(attempts)
                except StageError as exc:
                    last_error = exc
                    outcome = StageOutcome.failed
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    outcome = StageOutcome.failed
                    break
            ended = monotonic()
            sr = StageResult(
                stage=stage,
                outcome=outcome,
                started_at=started,
                ended_at=ended,
                error=str(last_error) if last_error else None,
                attempts=attempts,
            )
            results.append(sr)
            await self._emit_progress(ctx, stage, outcome, sr)
            if outcome is StageOutcome.failed:
                await self._emit_error(ctx, stage, last_error or RuntimeError("unknown"))
                reason = f"{stage.value}: {last_error}"
                await self._quarantine(ctx.document_id, reason)
                return PipelineResult(
                    job_id=ctx.job_id,
                    document_id=ctx.document_id,
                    success=False,
                    stages=results,
                    quarantine_reason=reason,
                )
        await self._mark_indexed(ctx.document_id)
        return PipelineResult(
            job_id=ctx.job_id,
            document_id=ctx.document_id,
            success=True,
            stages=results,
        )

    async def run_many(self, ctxs: Iterable[StageCtx]) -> list[PipelineResult]:
        """Process docs sequentially with per-doc isolation."""
        results: list[PipelineResult] = []
        for c in ctxs:
            try:
                results.append(await self.run(c))
            except Exception as exc:  # belt + braces — runner should not raise
                logger.exception(
                    "pipeline_run_unexpected_error",
                    extra={"document_id": c.document_id, "err": str(exc)},
                )
                results.append(
                    PipelineResult(
                        job_id=c.job_id,
                        document_id=c.document_id,
                        success=False,
                        quarantine_reason=f"runner: {exc}",
                    )
                )
        return results

    # ── hooks ────────────────────────────────────────────────────────────

    async def _sleep_backoff(self, attempt: int) -> None:
        base = self.deps.backoff_base
        if base <= 0:
            return
        await asyncio.sleep(base * (2 ** (attempt - 1)))

    async def _emit_progress(
        self, ctx: StageCtx, stage: Stage, outcome: StageOutcome, sr: StageResult
    ) -> None:
        if self.deps.on_progress is None:
            return
        try:
            r = self.deps.on_progress(ctx, stage, outcome, sr)
            if asyncio.iscoroutine(r):
                await r
        except Exception:  # noqa: BLE001
            logger.exception("pipeline_on_progress_failed")

    async def _emit_error(
        self, ctx: StageCtx, stage: Stage, exc: BaseException
    ) -> None:
        if self.deps.on_error is None:
            return
        try:
            r = self.deps.on_error(ctx, stage, exc)
            if asyncio.iscoroutine(r):
                await r
        except Exception:  # noqa: BLE001
            logger.exception("pipeline_on_error_failed")

    async def _quarantine(self, document_id: str, reason: str) -> None:
        if self.deps.quarantine_doc is None:
            return
        try:
            r = self.deps.quarantine_doc(document_id, reason)
            if asyncio.iscoroutine(r):
                await r
        except Exception:  # noqa: BLE001
            logger.exception("pipeline_quarantine_failed")

    async def _mark_indexed(self, document_id: str) -> None:
        if self.deps.mark_indexed is None:
            return
        try:
            r = self.deps.mark_indexed(document_id)
            if asyncio.iscoroutine(r):
                await r
        except Exception:  # noqa: BLE001
            logger.exception("pipeline_mark_indexed_failed")


__all__ = [
    "PipelineDeps",
    "PipelineResult",
    "PipelineRunner",
    "ProgressHook",
    "RetryableStageError",
    "STAGES",
    "Stage",
    "StageCtx",
    "StageError",
    "StageFn",
    "StageOutcome",
    "StageResult",
]
