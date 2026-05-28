"""RAG eval service — CRUD over ``kb_evals`` + ``kb_eval_runs``.

Owns persistence; delegates execution to :class:`EvalRunner`. Regression
detection compares each new run's ``pass_rate`` against the most recent
prior run on the same eval; on regression, fires the ``kb.eval.regression``
webhook (via control-plane stub).
"""
from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.control_plane.webhook_stub import emit_webhook
from ai_portal.knowledge_base.model import KbEval, KbEvalRun
from ai_portal.rag.eval.runner import EvalRunner, RetrieveFn, RunOutcome
from ai_portal.rag.eval.schemas import (
    EvalRecord,
    EvalRunRowResult,
    EvalRunSummary,
)


@dataclass(frozen=True)
class EvalView:
    id: _uuid.UUID
    kb_id: int
    name: str
    records: list[EvalRecord]
    judge_model: str | None
    judge_temperature: float
    created_at: Any
    updated_at: Any


@dataclass(frozen=True)
class EvalRunView:
    id: _uuid.UUID
    eval_id: _uuid.UUID
    snapshot_id: str | None
    summary: EvalRunSummary
    results: list[EvalRunRowResult]
    regression: bool
    ran_at: Any


def _records_from_blob(blob: dict | list) -> list[EvalRecord]:
    if isinstance(blob, list):
        items = blob
    elif isinstance(blob, dict):
        items = blob.get("records") or []
    else:
        items = []
    out: list[EvalRecord] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        try:
            out.append(EvalRecord.model_validate(raw))
        except Exception:  # noqa: BLE001
            continue
    return out


def _eval_to_view(row: KbEval) -> EvalView:
    return EvalView(
        id=row.id,
        kb_id=row.kb_id,
        name=row.name,
        records=_records_from_blob(row.test_set_json or {}),
        judge_model=row.judge_model,
        judge_temperature=row.judge_temperature,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _run_to_view(row: KbEvalRun) -> EvalRunView:
    summary = EvalRunSummary.model_validate(row.metrics_json or {})
    results = [EvalRunRowResult.model_validate(r) for r in (row.results_json or [])]
    return EvalRunView(
        id=row.id,
        eval_id=row.eval_id,
        snapshot_id=row.snapshot_id,
        summary=summary,
        results=results,
        regression=row.regression,
        ran_at=row.ran_at,
    )


class KbEvalsService:
    """CRUD + execution orchestrator for KB evals."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── test set CRUD ───────────────────────────────────────────────────

    def list_evals(self, *, kb_id: int) -> list[EvalView]:
        rows = self.db.scalars(
            select(KbEval)
            .where(KbEval.kb_id == kb_id)
            .order_by(KbEval.updated_at.desc())
        )
        return [_eval_to_view(r) for r in rows]

    def create_eval(
        self,
        *,
        kb_id: int,
        name: str,
        records: list[EvalRecord],
        judge_model: str | None = None,
        judge_temperature: float = 0.0,
    ) -> EvalView:
        row = KbEval(
            kb_id=kb_id,
            name=name,
            test_set_json={"records": [r.model_dump() for r in records]},
            judge_model=judge_model,
            judge_temperature=judge_temperature,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return _eval_to_view(row)

    def update_eval(
        self,
        *,
        kb_id: int,
        eval_id: _uuid.UUID,
        name: str | None = None,
        records: list[EvalRecord] | None = None,
        judge_model: str | None = None,
        judge_temperature: float | None = None,
    ) -> EvalView | None:
        row = self.db.get(KbEval, eval_id)
        if row is None or row.kb_id != kb_id:
            return None
        if name is not None:
            row.name = name
        if records is not None:
            row.test_set_json = {"records": [r.model_dump() for r in records]}
        if judge_model is not None:
            row.judge_model = judge_model
        if judge_temperature is not None:
            row.judge_temperature = judge_temperature
        self.db.commit()
        self.db.refresh(row)
        return _eval_to_view(row)

    def get_eval(self, *, kb_id: int, eval_id: _uuid.UUID) -> EvalView | None:
        row = self.db.get(KbEval, eval_id)
        if row is None or row.kb_id != kb_id:
            return None
        return _eval_to_view(row)

    def delete_eval(self, *, kb_id: int, eval_id: _uuid.UUID) -> bool:
        row = self.db.get(KbEval, eval_id)
        if row is None or row.kb_id != kb_id:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    # ── run persistence ─────────────────────────────────────────────────

    def list_runs(self, *, kb_id: int, eval_id: _uuid.UUID) -> list[EvalRunView]:
        rows = self.db.scalars(
            select(KbEvalRun)
            .join(KbEval, KbEval.id == KbEvalRun.eval_id)
            .where(KbEval.kb_id == kb_id, KbEvalRun.eval_id == eval_id)
            .order_by(KbEvalRun.ran_at.desc())
        )
        return [_run_to_view(r) for r in rows]

    def get_previous_run(self, *, eval_id: _uuid.UUID) -> EvalRunView | None:
        row = self.db.scalars(
            select(KbEvalRun)
            .where(KbEvalRun.eval_id == eval_id)
            .order_by(KbEvalRun.ran_at.desc())
            .limit(1)
        ).first()
        return _run_to_view(row) if row is not None else None

    def _persist_run(
        self,
        *,
        eval_id: _uuid.UUID,
        outcome: RunOutcome,
        snapshot_id: str | None,
    ) -> EvalRunView:
        row = KbEvalRun(
            eval_id=eval_id,
            snapshot_id=snapshot_id,
            metrics_json=outcome.summary.model_dump(),
            results_json=[r.model_dump() for r in outcome.results],
            regression=bool(outcome.summary.regression),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return _run_to_view(row)

    async def run_eval(
        self,
        *,
        kb_id: int,
        eval_id: _uuid.UUID,
        retrieve: RetrieveFn,
        snapshot_id: str | None = None,
        regression_threshold: float = 0.05,
        primary_metric: str = "recall@5",
        org_id: _uuid.UUID | None = None,
    ) -> EvalRunView | None:
        """Execute the eval and persist the run. On regression, emit webhook."""
        view = self.get_eval(kb_id=kb_id, eval_id=eval_id)
        if view is None:
            return None
        runner = EvalRunner(
            retrieve=retrieve,
            regression_threshold=regression_threshold,
            primary_metric=primary_metric,
        )
        previous = self.get_previous_run(eval_id=eval_id)
        outcome = await runner.run(
            view.records,
            previous_summary=previous.summary if previous else None,
        )
        persisted = self._persist_run(
            eval_id=eval_id, outcome=outcome, snapshot_id=snapshot_id
        )
        if persisted.regression and org_id is not None:
            emit_webhook(
                "kb.eval.regression",
                {
                    "kb_id": kb_id,
                    "eval_id": str(eval_id),
                    "run_id": str(persisted.id),
                    "delta": outcome.summary.regression_delta,
                    "pass_rate": outcome.summary.pass_rate,
                    "primary_metric": primary_metric,
                },
                org_id,
            )
        return persisted


__all__ = ["EvalRunView", "EvalView", "KbEvalsService"]
