"""Eval-service regression → webhook firing.

Drives ``KbEvalsService.run_eval`` directly with monkeypatched persistence
hooks + a stubbed webhook emitter. No DB session is required because we
short-circuit every DB-touching method on the service.
"""
from __future__ import annotations

import uuid as _uuid
from dataclasses import replace

import pytest

from ai_portal.rag.eval import service as svc_module
from ai_portal.rag.eval.schemas import EvalRecord, EvalRunSummary
from ai_portal.rag.eval.service import EvalRunView, EvalView, KbEvalsService


def _eval_view(*, eval_id: _uuid.UUID, kb_id: int = 1) -> EvalView:
    return EvalView(
        id=eval_id,
        kb_id=kb_id,
        name="t",
        records=[
            EvalRecord(
                id="r1",
                query="q",
                expected_doc_ids=["a"],
                judges=["recall@5"],
            )
        ],
        judge_model=None,
        judge_temperature=0.0,
        created_at=None,
        updated_at=None,
    )


def _run_view(*, eval_id: _uuid.UUID, pass_rate: float, regression: bool) -> EvalRunView:
    return EvalRunView(
        id=_uuid.uuid4(),
        eval_id=eval_id,
        snapshot_id=None,
        summary=EvalRunSummary(pass_rate=pass_rate, n=1, regression=regression),
        results=[],
        regression=regression,
        ran_at=None,
    )


class _SvcStub(KbEvalsService):
    """Bypass every DB-bound method while keeping orchestration logic."""

    def __init__(self, *, view: EvalView, previous: EvalRunView | None) -> None:
        self._view = view
        self._previous = previous
        self.persisted: EvalRunView | None = None

    def get_eval(self, *, kb_id, eval_id):  # type: ignore[override]
        return self._view if self._view.kb_id == kb_id else None

    def get_previous_run(self, *, eval_id):  # type: ignore[override]
        return self._previous

    def _persist_run(self, *, eval_id, outcome, snapshot_id):  # type: ignore[override]
        persisted = EvalRunView(
            id=_uuid.uuid4(),
            eval_id=eval_id,
            snapshot_id=snapshot_id,
            summary=outcome.summary,
            results=outcome.results,
            regression=bool(outcome.summary.regression),
            ran_at=None,
        )
        self.persisted = persisted
        return persisted


@pytest.fixture
def emitted(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Capture every webhook emitted during the test."""
    captured: list[tuple] = []

    def _capture(event_type, payload, org_id):
        captured.append((event_type, payload, org_id))

    monkeypatch.setattr(svc_module, "emit_webhook", _capture)
    return captured


@pytest.mark.asyncio
async def test_regression_below_threshold_fires_webhook(emitted) -> None:
    eval_id = _uuid.uuid4()
    org_id = _uuid.uuid4()
    previous = _run_view(eval_id=eval_id, pass_rate=0.9, regression=False)
    s = _SvcStub(view=_eval_view(eval_id=eval_id), previous=previous)

    # Make retrieval return nothing so recall@5 = 0 → big drop from 0.9
    async def retrieve(_q: str) -> list[str]:
        return []

    out = await s.run_eval(
        kb_id=1,
        eval_id=eval_id,
        retrieve=retrieve,
        regression_threshold=0.1,
        org_id=org_id,
    )
    assert out is not None
    assert out.regression is True
    assert len(emitted) == 1
    event, payload, emitted_org = emitted[0]
    assert event == "kb.eval.regression"
    assert payload["kb_id"] == 1
    assert payload["eval_id"] == str(eval_id)
    assert payload["pass_rate"] == 0.0
    assert payload["delta"] < -0.1
    assert emitted_org == org_id


@pytest.mark.asyncio
async def test_no_regression_does_not_fire_webhook(emitted) -> None:
    eval_id = _uuid.uuid4()
    org_id = _uuid.uuid4()
    previous = _run_view(eval_id=eval_id, pass_rate=0.5, regression=False)
    s = _SvcStub(view=_eval_view(eval_id=eval_id), previous=previous)

    async def retrieve(_q: str) -> list[str]:
        return ["a"]  # recall@5 = 1.0; way above previous

    out = await s.run_eval(
        kb_id=1,
        eval_id=eval_id,
        retrieve=retrieve,
        regression_threshold=0.1,
        org_id=org_id,
    )
    assert out is not None
    assert out.regression is False
    assert emitted == []


@pytest.mark.asyncio
async def test_no_previous_run_no_webhook(emitted) -> None:
    eval_id = _uuid.uuid4()
    org_id = _uuid.uuid4()
    s = _SvcStub(view=_eval_view(eval_id=eval_id), previous=None)

    async def retrieve(_q: str) -> list[str]:
        return []

    out = await s.run_eval(
        kb_id=1,
        eval_id=eval_id,
        retrieve=retrieve,
        regression_threshold=0.1,
        org_id=org_id,
    )
    assert out is not None
    assert out.regression is False
    assert emitted == []


@pytest.mark.asyncio
async def test_regression_without_org_id_skips_webhook(emitted) -> None:
    eval_id = _uuid.uuid4()
    previous = _run_view(eval_id=eval_id, pass_rate=0.9, regression=False)
    s = _SvcStub(view=_eval_view(eval_id=eval_id), previous=previous)

    async def retrieve(_q: str) -> list[str]:
        return []

    out = await s.run_eval(
        kb_id=1,
        eval_id=eval_id,
        retrieve=retrieve,
        regression_threshold=0.1,
    )
    assert out is not None
    assert out.regression is True
    assert emitted == []


@pytest.mark.asyncio
async def test_missing_eval_returns_none(emitted) -> None:
    s = _SvcStub(view=_eval_view(eval_id=_uuid.uuid4(), kb_id=999), previous=None)

    async def retrieve(_q: str) -> list[str]:
        return []

    out = await s.run_eval(
        kb_id=1,  # mismatch
        eval_id=_uuid.uuid4(),
        retrieve=retrieve,
        regression_threshold=0.1,
        org_id=_uuid.uuid4(),
    )
    assert out is None
    assert emitted == []
