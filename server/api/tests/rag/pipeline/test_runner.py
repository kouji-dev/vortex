"""Pipeline runner behaviour: happy path, failure isolation, retries."""
from __future__ import annotations

import pytest

from ai_portal.rag.pipeline.runner import (
    PipelineDeps,
    PipelineRunner,
    RetryableStageError,
    STAGES,
    Stage,
    StageCtx,
    StageError,
    StageOutcome,
)


def _ctx(**over) -> StageCtx:
    base = StageCtx(
        job_id="j1",
        document_id="d1",
        kb_id="kb1",
        source_uri="file://x",
        mime="text/plain",
    )
    for k, v in over.items():
        setattr(base, k, v)
    return base


@pytest.mark.asyncio
async def test_happy_path_records_all_eight_stages():
    calls: list[Stage] = []

    async def make_stage(stage: Stage):
        async def fn(ctx):
            calls.append(stage)
            return ctx

        return fn

    stages = {s: await make_stage(s) for s in STAGES}
    runner = PipelineRunner(PipelineDeps(stages=stages))
    res = await runner.run(_ctx())
    assert res.success
    assert [s.value for s in calls] == [s.value for s in STAGES]
    assert [r.stage for r in res.stages] == list(STAGES)
    assert all(r.outcome is StageOutcome.ok for r in res.stages)


@pytest.mark.asyncio
async def test_failure_at_embed_quarantines_doc_and_stops_pipeline():
    quarantined: list[tuple[str, str]] = []

    async def quarantine(doc_id: str, reason: str) -> None:
        quarantined.append((doc_id, reason))

    async def noop(ctx):
        return ctx

    async def boom_embed(ctx):
        raise RuntimeError("embedder offline")

    stages = {s: noop for s in STAGES}
    stages[Stage.embed] = boom_embed

    runner = PipelineRunner(
        PipelineDeps(stages=stages, quarantine_doc=quarantine)
    )
    res = await runner.run(_ctx())
    assert not res.success
    assert res.quarantine_reason and "embedder offline" in res.quarantine_reason
    # index stage must NOT have run.
    stage_names = [r.stage for r in res.stages]
    assert Stage.index not in stage_names
    # Quarantine hook fired once.
    assert quarantined == [("d1", res.quarantine_reason)]


@pytest.mark.asyncio
async def test_retryable_error_succeeds_after_backoff():
    attempts = {"n": 0}

    async def flaky(ctx):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RetryableStageError(Stage.embed, "transient")
        return ctx

    async def noop(ctx):
        return ctx

    stages = {s: noop for s in STAGES}
    stages[Stage.embed] = flaky

    runner = PipelineRunner(
        PipelineDeps(stages=stages, retries={Stage.embed: 5}, backoff_base=0.0)
    )
    res = await runner.run(_ctx())
    assert res.success
    embed_step = next(r for r in res.stages if r.stage is Stage.embed)
    assert embed_step.attempts == 3
    assert embed_step.outcome is StageOutcome.ok


@pytest.mark.asyncio
async def test_retryable_error_exceeding_budget_quarantines():
    async def always_flaky(ctx):
        raise RetryableStageError(Stage.embed, "still down")

    async def noop(ctx):
        return ctx

    stages = {s: noop for s in STAGES}
    stages[Stage.embed] = always_flaky

    runner = PipelineRunner(
        PipelineDeps(stages=stages, retries={Stage.embed: 1}, backoff_base=0.0)
    )
    res = await runner.run(_ctx())
    assert not res.success
    embed_step = next(r for r in res.stages if r.stage is Stage.embed)
    assert embed_step.attempts == 2  # 1 initial + 1 retry
    assert embed_step.outcome is StageOutcome.failed


@pytest.mark.asyncio
async def test_progress_hook_called_per_stage():
    events: list[tuple[Stage, StageOutcome]] = []

    async def noop(ctx):
        return ctx

    def on_progress(ctx, stage, outcome, sr):
        events.append((stage, outcome))

    runner = PipelineRunner(
        PipelineDeps(stages={s: noop for s in STAGES}, on_progress=on_progress)
    )
    await runner.run(_ctx())
    assert [e[0] for e in events] == list(STAGES)
    assert all(o is StageOutcome.ok for _, o in events)


@pytest.mark.asyncio
async def test_run_many_isolates_failures():
    async def noop(ctx):
        return ctx

    async def boom(ctx):
        if ctx.document_id == "bad":
            raise StageError(Stage.extract, "kaboom")
        return ctx

    stages = {s: noop for s in STAGES}
    stages[Stage.extract] = boom

    runner = PipelineRunner(PipelineDeps(stages=stages))
    ctxs = [
        _ctx(document_id="ok1"),
        _ctx(document_id="bad"),
        _ctx(document_id="ok2"),
    ]
    results = await runner.run_many(ctxs)
    assert [r.success for r in results] == [True, False, True]
