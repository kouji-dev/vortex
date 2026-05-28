"""Eval service — CRUD over ``model_evals`` + ``model_eval_runs``.

Owns persistence; delegates execution to :class:`EvalRunner`.
Regression detection compares each new run's pass_rate against the most
recent prior run on the same ``(eval_id, target_model)``.
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.gateway.evals.model import ModelEval, ModelEvalRun
from ai_portal.gateway.evals.runner import (
    EvalRunner,
    RunOutcome,
    make_actor_for_run,
)
from ai_portal.gateway.evals.schemas import (
    EvalRecord,
    EvalRunRowResult,
    EvalRunSummary,
)


@dataclass(frozen=True)
class EvalView:
    """Service-layer view of a saved eval (test set)."""

    id: _uuid.UUID
    name: str
    records: list[EvalRecord]
    created_at: object
    updated_at: object


@dataclass(frozen=True)
class EvalRunView:
    """Service-layer view of one persisted eval run."""

    id: _uuid.UUID
    eval_id: _uuid.UUID
    target_model: str
    summary: EvalRunSummary
    results: list[EvalRunRowResult]
    ran_at: object


def _records_from_blob(blob: dict | list) -> list[EvalRecord]:
    """Normalise the persisted ``test_set_json`` into typed records."""
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


def _eval_to_view(row: ModelEval) -> EvalView:
    return EvalView(
        id=row.id,
        name=row.name,
        records=_records_from_blob(row.test_set_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _run_to_view(row: ModelEvalRun) -> EvalRunView:
    summary = EvalRunSummary.model_validate(row.summary_json or {})
    results = [EvalRunRowResult.model_validate(r) for r in (row.results_json or [])]
    return EvalRunView(
        id=row.id,
        eval_id=row.eval_id,
        target_model=row.target_model,
        summary=summary,
        results=results,
        ran_at=row.ran_at,
    )


class EvalsService:
    """CRUD + execution orchestrator."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── test set CRUD ───────────────────────────────────────────────────

    def list_evals(self, *, org_id: _uuid.UUID) -> list[EvalView]:
        rows = self.db.scalars(
            select(ModelEval)
            .where(ModelEval.org_id == org_id)
            .order_by(ModelEval.updated_at.desc())
        )
        return [_eval_to_view(r) for r in rows]

    def create_eval(
        self,
        *,
        org_id: _uuid.UUID,
        name: str,
        records: list[EvalRecord],
    ) -> EvalView:
        row = ModelEval(
            org_id=org_id,
            name=name,
            test_set_json={"records": [r.model_dump() for r in records]},
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return _eval_to_view(row)

    def update_eval(
        self,
        *,
        org_id: _uuid.UUID,
        eval_id: _uuid.UUID,
        name: str | None = None,
        records: list[EvalRecord] | None = None,
    ) -> EvalView | None:
        row = self.db.get(ModelEval, eval_id)
        if row is None or row.org_id != org_id:
            return None
        if name is not None:
            row.name = name
        if records is not None:
            row.test_set_json = {"records": [r.model_dump() for r in records]}
        self.db.commit()
        self.db.refresh(row)
        return _eval_to_view(row)

    def get_eval(self, *, org_id: _uuid.UUID, eval_id: _uuid.UUID) -> EvalView | None:
        row = self.db.get(ModelEval, eval_id)
        if row is None or row.org_id != org_id:
            return None
        return _eval_to_view(row)

    def delete_eval(self, *, org_id: _uuid.UUID, eval_id: _uuid.UUID) -> bool:
        row = self.db.get(ModelEval, eval_id)
        if row is None or row.org_id != org_id:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    # ── run persistence + retrieval ─────────────────────────────────────

    def list_runs(
        self, *, org_id: _uuid.UUID, eval_id: _uuid.UUID
    ) -> list[EvalRunView]:
        rows = self.db.scalars(
            select(ModelEvalRun)
            .where(
                ModelEvalRun.org_id == org_id,
                ModelEvalRun.eval_id == eval_id,
            )
            .order_by(ModelEvalRun.ran_at.desc())
        )
        return [_run_to_view(r) for r in rows]

    def get_previous_run(
        self,
        *,
        org_id: _uuid.UUID,
        eval_id: _uuid.UUID,
        target_model: str,
    ) -> EvalRunView | None:
        row = self.db.scalars(
            select(ModelEvalRun)
            .where(
                ModelEvalRun.org_id == org_id,
                ModelEvalRun.eval_id == eval_id,
                ModelEvalRun.target_model == target_model,
            )
            .order_by(ModelEvalRun.ran_at.desc())
            .limit(1)
        ).first()
        return _run_to_view(row) if row is not None else None

    def _persist_run(
        self,
        *,
        org_id: _uuid.UUID,
        eval_id: _uuid.UUID,
        outcome: RunOutcome,
    ) -> EvalRunView:
        row = ModelEvalRun(
            org_id=org_id,
            eval_id=eval_id,
            target_model=outcome.target_model,
            summary_json=outcome.summary.model_dump(),
            results_json=[r.model_dump() for r in outcome.results],
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return _run_to_view(row)

    async def run_eval(
        self,
        *,
        org_id: _uuid.UUID,
        eval_id: _uuid.UUID,
        target_models: list[str],
        user_id: int | None,
        regression_threshold: float = 0.05,
    ) -> list[EvalRunView]:
        """Execute the eval against ``target_models`` and persist each run."""
        view = self.get_eval(org_id=org_id, eval_id=eval_id)
        if view is None:
            return []
        runner = EvalRunner(regression_threshold=regression_threshold)
        actor = make_actor_for_run(org_id=org_id, user_id=user_id)

        out: list[EvalRunView] = []
        for model in target_models:
            outcome = await runner.run(
                records=view.records,
                target_model=model,
                actor=actor,
            )
            # Look up most recent prior run for regression diff.
            prev = self.get_previous_run(
                org_id=org_id, eval_id=eval_id, target_model=model
            )
            outcome.summary = runner.detect_regression(
                current=outcome.summary,
                previous=prev.summary if prev else None,
            )
            persisted = self._persist_run(
                org_id=org_id, eval_id=eval_id, outcome=outcome
            )
            out.append(persisted)
        return out


__all__ = ["EvalRunView", "EvalView", "EvalsService"]
