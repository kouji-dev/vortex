"""Gateway evals HTTP surface.

Routes:

- ``GET    /v1/gateway/evals``                    — list test sets
- ``POST   /v1/gateway/evals``                    — create a test set
- ``GET    /v1/gateway/evals/{id}``               — fetch one test set
- ``PUT    /v1/gateway/evals/{id}``               — update a test set
- ``DELETE /v1/gateway/evals/{id}``               — delete a test set
- ``POST   /v1/gateway/evals/{id}/run``           — run against N models
- ``GET    /v1/gateway/evals/{id}/runs``          — list prior runs
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_db
from ai_portal.control_plane.deps import require_actor
from ai_portal.gateway.evals.schemas import (
    EvalRunOut,
    EvalRunRequest,
    EvalRunResponse,
    EvalRunRowResult,
    EvalRunSummary,
    EvalTestSetIn,
    EvalTestSetOut,
)
from ai_portal.gateway.evals.service import (
    EvalRunView,
    EvalsService,
    EvalView,
)
from ai_portal.rbac.service import Actor

router = APIRouter(prefix="/v1/gateway/evals", tags=["gateway-evals"])


def get_evals_service(db: Session = Depends(get_db)) -> EvalsService:
    """FastAPI dep returning the evals service. Overridable in tests."""
    return EvalsService(db)


def _eval_to_out(v: EvalView) -> EvalTestSetOut:
    return EvalTestSetOut(
        id=str(v.id),
        name=v.name,
        records=v.records,
        created_at=v.created_at,  # type: ignore[arg-type]
        updated_at=v.updated_at,  # type: ignore[arg-type]
    )


def _run_to_out(v: EvalRunView) -> EvalRunOut:
    return EvalRunOut(
        id=str(v.id),
        eval_id=str(v.eval_id),
        target_model=v.target_model,
        summary=v.summary,
        results=v.results,
        ran_at=v.ran_at,  # type: ignore[arg-type]
    )


# ── test sets ────────────────────────────────────────────────────────────


@router.get("", response_model=list[EvalTestSetOut])
def list_evals(
    actor: Actor = Depends(require_actor),
    svc: EvalsService = Depends(get_evals_service),
) -> list[EvalTestSetOut]:
    return [_eval_to_out(v) for v in svc.list_evals(org_id=actor.org_id)]


@router.post(
    "",
    response_model=EvalTestSetOut,
    status_code=status.HTTP_201_CREATED,
)
def create_eval(
    body: EvalTestSetIn,
    actor: Actor = Depends(require_actor),
    svc: EvalsService = Depends(get_evals_service),
) -> EvalTestSetOut:
    view = svc.create_eval(org_id=actor.org_id, name=body.name, records=body.records)
    return _eval_to_out(view)


@router.get("/{eval_id}", response_model=EvalTestSetOut)
def get_eval(
    eval_id: uuid.UUID,
    actor: Actor = Depends(require_actor),
    svc: EvalsService = Depends(get_evals_service),
) -> EvalTestSetOut:
    view = svc.get_eval(org_id=actor.org_id, eval_id=eval_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="eval not found")
    return _eval_to_out(view)


@router.put("/{eval_id}", response_model=EvalTestSetOut)
def update_eval(
    eval_id: uuid.UUID,
    body: EvalTestSetIn,
    actor: Actor = Depends(require_actor),
    svc: EvalsService = Depends(get_evals_service),
) -> EvalTestSetOut:
    view = svc.update_eval(
        org_id=actor.org_id,
        eval_id=eval_id,
        name=body.name,
        records=body.records,
    )
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="eval not found")
    return _eval_to_out(view)


@router.delete("/{eval_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_eval(
    eval_id: uuid.UUID,
    actor: Actor = Depends(require_actor),
    svc: EvalsService = Depends(get_evals_service),
) -> None:
    if not svc.delete_eval(org_id=actor.org_id, eval_id=eval_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="eval not found")


# ── runs ─────────────────────────────────────────────────────────────────


@router.post("/{eval_id}/run", response_model=EvalRunResponse)
async def run_eval(
    eval_id: uuid.UUID,
    body: EvalRunRequest,
    actor: Actor = Depends(require_actor),
    svc: EvalsService = Depends(get_evals_service),
) -> EvalRunResponse:
    views = await svc.run_eval(
        org_id=actor.org_id,
        eval_id=eval_id,
        target_models=body.target_models,
        user_id=actor.user_id,
        regression_threshold=body.regression_threshold,
    )
    if not views and body.target_models:
        # Eval not found: empty target_models legitimately returns [].
        if svc.get_eval(org_id=actor.org_id, eval_id=eval_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="eval not found")
    return EvalRunResponse(runs=[_run_to_out(v) for v in views])


@router.get("/{eval_id}/runs", response_model=list[EvalRunOut])
def list_runs(
    eval_id: uuid.UUID,
    actor: Actor = Depends(require_actor),
    svc: EvalsService = Depends(get_evals_service),
) -> list[EvalRunOut]:
    return [_run_to_out(v) for v in svc.list_runs(org_id=actor.org_id, eval_id=eval_id)]


__all__ = [
    "EvalRunOut",
    "EvalRunRowResult",
    "EvalRunSummary",
    "get_evals_service",
    "router",
]
