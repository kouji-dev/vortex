"""HTTP surface for KB evals, playground, analytics.

Routes:
    GET    /api/kbs/{kb_id}/evals
    POST   /api/kbs/{kb_id}/evals
    GET    /api/kbs/{kb_id}/evals/{eval_id}
    PATCH  /api/kbs/{kb_id}/evals/{eval_id}
    DELETE /api/kbs/{kb_id}/evals/{eval_id}
    POST   /api/kbs/{kb_id}/evals/{eval_id}/run
    GET    /api/kbs/{kb_id}/evals/{eval_id}/runs

    POST   /api/kbs/{kb_id}/playground
    GET    /api/kbs/{kb_id}/playground/sessions
    GET    /api/kbs/{kb_id}/playground/sessions/{session_id}
    DELETE /api/kbs/{kb_id}/playground/sessions/{session_id}

    GET    /api/kbs/{kb_id}/analytics
    POST   /api/kbs/{kb_id}/feedback
"""
from __future__ import annotations

import logging
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_org_id, get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.knowledge_base import service as kb_svc
from ai_portal.rag.analytics.rollups import KbAnalyticsService
from ai_portal.rag.analytics.schemas import (
    AnalyticsOverview,
    FeedbackIn,
)
from ai_portal.rag.management.doc_detail import DocDetailOut, fetch_doc_detail
from ai_portal.rag.eval.runner import RetrieveFn
from ai_portal.rag.eval.schemas import (
    EvalRecord,
    EvalRunOut,
    EvalRunRequest,
    EvalRunRowResult,
    EvalRunSummary,
    EvalTestSetIn,
    EvalTestSetOut,
)
from ai_portal.rag.eval.service import EvalRunView, KbEvalsService
from ai_portal.rag.playground.schemas import (
    PlaygroundRequest,
    PlaygroundResponse,
    PlaygroundSessionOut,
    PlaygroundSettings,
    RetrievedChunk,
)
from ai_portal.rag.playground.service import KbPlaygroundService
from ai_portal.rag.search.hybrid import hybrid_search
from ai_portal.rag.search.types import SearchFilter, SearchRequest

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kbs", tags=["rag-management"])


# ── helpers ──────────────────────────────────────────────────────────────


def _check_kb_access(db: Session, user: User, kb_id: int) -> None:
    """Raise 404 unless the user owns the KB. Re-uses kb_svc logic."""
    kb_svc.get_owned_kb(db, user, kb_id)


def _run_view_to_out(view: EvalRunView, eval_id: _uuid.UUID) -> EvalRunOut:
    return EvalRunOut(
        id=view.id,
        eval_id=eval_id,
        snapshot_id=view.snapshot_id,
        summary=view.summary,
        results=view.results,
        regression=view.regression,
        ran_at=view.ran_at,
    )


def _make_retrieve(db: Session, kb_id: int, user: User) -> RetrieveFn:
    """Build a retrieval callable bound to a KB + actor for eval runs."""

    async def _retrieve(query: str) -> list[str]:
        req = SearchRequest(
            query=query,
            kb_ids=[kb_id],
            top_k=10,
            filter=SearchFilter(),
            actor_user_id=str(user.id),
            rerank=False,
        )
        hits = hybrid_search(db, req)
        return [h.document_id for h in hits]

    return _retrieve


def _make_playground_retrieve(db: Session, user: User):
    async def _retrieve(kb_id: int, query: str, settings: PlaygroundSettings):
        req = SearchRequest(
            query=query,
            kb_ids=[kb_id],
            top_k=settings.top_k,
            filter=SearchFilter(),
            actor_user_id=str(user.id),
            rerank=settings.rerank,
        )
        hits = hybrid_search(db, req)
        return [
            RetrievedChunk(
                chunk_id=h.chunk_id,
                document_id=h.document_id,
                text=h.text,
                score=h.score,
                meta=h.meta or {},
            )
            for h in hits
        ]

    return _retrieve


# ── eval routes ──────────────────────────────────────────────────────────


@router.get("/{kb_id}/evals", response_model=list[EvalTestSetOut])
def list_evals(
    kb_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_kb_access(db, user, kb_id)
    svc = KbEvalsService(db)
    return [
        EvalTestSetOut(
            id=v.id,
            kb_id=v.kb_id,
            name=v.name,
            records=v.records,
            judge_model=v.judge_model,
            judge_temperature=v.judge_temperature,
            created_at=v.created_at,
            updated_at=v.updated_at,
        )
        for v in svc.list_evals(kb_id=kb_id)
    ]


@router.post("/{kb_id}/evals", response_model=EvalTestSetOut, status_code=201)
def create_eval(
    kb_id: int,
    body: EvalTestSetIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_kb_access(db, user, kb_id)
    svc = KbEvalsService(db)
    v = svc.create_eval(
        kb_id=kb_id,
        name=body.name,
        records=body.records,
        judge_model=body.judge_model,
        judge_temperature=body.judge_temperature,
    )
    return EvalTestSetOut(
        id=v.id,
        kb_id=v.kb_id,
        name=v.name,
        records=v.records,
        judge_model=v.judge_model,
        judge_temperature=v.judge_temperature,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


@router.get("/{kb_id}/evals/{eval_id}", response_model=EvalTestSetOut)
def get_eval(
    kb_id: int,
    eval_id: _uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_kb_access(db, user, kb_id)
    svc = KbEvalsService(db)
    v = svc.get_eval(kb_id=kb_id, eval_id=eval_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Eval not found")
    return EvalTestSetOut(
        id=v.id,
        kb_id=v.kb_id,
        name=v.name,
        records=v.records,
        judge_model=v.judge_model,
        judge_temperature=v.judge_temperature,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


@router.patch("/{kb_id}/evals/{eval_id}", response_model=EvalTestSetOut)
def update_eval(
    kb_id: int,
    eval_id: _uuid.UUID,
    body: EvalTestSetIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_kb_access(db, user, kb_id)
    svc = KbEvalsService(db)
    v = svc.update_eval(
        kb_id=kb_id,
        eval_id=eval_id,
        name=body.name,
        records=body.records,
        judge_model=body.judge_model,
        judge_temperature=body.judge_temperature,
    )
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Eval not found")
    return EvalTestSetOut(
        id=v.id,
        kb_id=v.kb_id,
        name=v.name,
        records=v.records,
        judge_model=v.judge_model,
        judge_temperature=v.judge_temperature,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


@router.delete("/{kb_id}/evals/{eval_id}", status_code=204)
def delete_eval(
    kb_id: int,
    eval_id: _uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_kb_access(db, user, kb_id)
    svc = KbEvalsService(db)
    if not svc.delete_eval(kb_id=kb_id, eval_id=eval_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Eval not found")


@router.post("/{kb_id}/evals/{eval_id}/run", response_model=EvalRunOut)
async def run_eval(
    kb_id: int,
    eval_id: _uuid.UUID,
    body: EvalRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
):
    _check_kb_access(db, user, kb_id)
    svc = KbEvalsService(db)
    view = await svc.run_eval(
        kb_id=kb_id,
        eval_id=eval_id,
        retrieve=_make_retrieve(db, kb_id, user),
        snapshot_id=body.snapshot_id,
        regression_threshold=body.regression_threshold,
        primary_metric=body.primary_metric,
        org_id=org_id,
    )
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Eval not found")
    return _run_view_to_out(view, eval_id)


@router.get("/{kb_id}/evals/{eval_id}/runs", response_model=list[EvalRunOut])
def list_runs(
    kb_id: int,
    eval_id: _uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_kb_access(db, user, kb_id)
    svc = KbEvalsService(db)
    return [_run_view_to_out(v, eval_id) for v in svc.list_runs(kb_id=kb_id, eval_id=eval_id)]


# ── playground routes ────────────────────────────────────────────────────


@router.post("/{kb_id}/playground", response_model=PlaygroundResponse)
async def run_playground(
    kb_id: int,
    body: PlaygroundRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_kb_access(db, user, kb_id)
    svc = KbPlaygroundService(
        db=db,
        retrieve=_make_playground_retrieve(db, user),
        answer=None,
    )
    return await svc.run(kb_id=kb_id, user_id=user.id, req=body)


@router.get("/{kb_id}/playground/sessions", response_model=list[PlaygroundSessionOut])
def list_playground_sessions(
    kb_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_kb_access(db, user, kb_id)
    svc = KbPlaygroundService(db=db, retrieve=_make_playground_retrieve(db, user))
    return svc.list_sessions(kb_id=kb_id)


@router.get(
    "/{kb_id}/playground/sessions/{session_id}", response_model=PlaygroundSessionOut
)
def get_playground_session(
    kb_id: int,
    session_id: _uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_kb_access(db, user, kb_id)
    svc = KbPlaygroundService(db=db, retrieve=_make_playground_retrieve(db, user))
    out = svc.get_session(kb_id=kb_id, session_id=session_id)
    if out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    return out


@router.delete("/{kb_id}/playground/sessions/{session_id}", status_code=204)
def delete_playground_session(
    kb_id: int,
    session_id: _uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_kb_access(db, user, kb_id)
    svc = KbPlaygroundService(db=db, retrieve=_make_playground_retrieve(db, user))
    if not svc.delete_session(kb_id=kb_id, session_id=session_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")


class _SaveAsEvalBody(BaseModel):
    test_set_id: _uuid.UUID


class _SaveAsEvalOut(BaseModel):
    record_id: str
    test_set_id: _uuid.UUID
    query: str
    expected_doc_ids: list[str]


@router.post(
    "/{kb_id}/playground/sessions/{session_id}/save-as-eval",
    response_model=_SaveAsEvalOut,
)
def save_session_as_eval(
    kb_id: int,
    session_id: _uuid.UUID,
    body: _SaveAsEvalBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Append the playground session as a new EvalRecord on ``test_set_id``."""
    _check_kb_access(db, user, kb_id)
    svc = KbPlaygroundService(db=db, retrieve=_make_playground_retrieve(db, user))
    rec = svc.save_as_eval_record(
        kb_id=kb_id, session_id=session_id, test_set_id=body.test_set_id
    )
    if rec is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Session or test set not found"
        )
    return _SaveAsEvalOut(
        record_id=rec.id,
        test_set_id=body.test_set_id,
        query=rec.query,
        expected_doc_ids=rec.expected_doc_ids,
    )


# ── version retention cleanup ────────────────────────────────────────────────


class _CleanupOut(BaseModel):
    kbs_processed: int
    documents_processed: int
    versions_deleted: int


@router.post(
    "/{kb_id}/maintenance/cleanup-versions",
    response_model=_CleanupOut,
)
def cleanup_versions(
    kb_id: int,
    keep_n: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Drop document versions older than the most recent ``keep_n``.

    When ``keep_n`` is omitted, falls back to the KB's
    ``settings_json.version_retention`` then the global default (10).
    """
    _check_kb_access(db, user, kb_id)
    from ai_portal.rag.workers.version_cleanup import cleanup_versions_for_kb

    rep = cleanup_versions_for_kb(db, kb_id=kb_id, keep_n=keep_n)
    return _CleanupOut(
        kbs_processed=rep.kbs_processed,
        documents_processed=rep.documents_processed,
        versions_deleted=rep.versions_deleted,
    )


# ── analytics routes ─────────────────────────────────────────────────────


@router.get("/{kb_id}/analytics", response_model=AnalyticsOverview)
def get_analytics(
    kb_id: int,
    window_days: int = 30,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_kb_access(db, user, kb_id)
    svc = KbAnalyticsService(db)
    return svc.overview(kb_id=kb_id, window_days=window_days)


class FeedbackOut(BaseModel):
    id: _uuid.UUID


@router.post("/{kb_id}/feedback", response_model=FeedbackOut, status_code=201)
def submit_feedback(
    kb_id: int,
    body: FeedbackIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_kb_access(db, user, kb_id)
    if body.rating not in ("up", "down"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="rating must be 'up' or 'down'"
        )
    svc = KbAnalyticsService(db)
    fid = svc.submit_feedback(
        kb_id=kb_id,
        user_id=user.id,
        rating=body.rating,
        query_id=_uuid.UUID(body.query_id) if body.query_id else None,
        chunk_id=_uuid.UUID(body.chunk_id) if body.chunk_id else None,
        comment=body.comment,
    )
    return FeedbackOut(id=fid)


# ── document detail (enriched with last sync error) ──────────────────────


@router.get(
    "/{kb_id}/documents/{doc_id}",
    response_model=DocDetailOut,
)
def get_document_detail(
    kb_id: int,
    doc_id: _uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocDetailOut:
    _check_kb_access(db, user, kb_id)
    out = fetch_doc_detail(db, kb_id=kb_id, doc_id=doc_id)
    if out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found")
    return out


__all__ = ["router"]
