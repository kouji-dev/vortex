"""RAG search + answer + search-provider HTTP surface.

Routes:
    POST /api/kbs/{id}/search                — hybrid search
    POST /api/kbs/{id}/answer                — streaming answer (SSE)
    POST /api/kbs/federated/answer           — federated streaming answer (SSE)
    POST /api/search                         — external/internal search providers

Author note: these routes intentionally re-use the FastAPI ``Depends``
helpers from the existing knowledge_base router so auth + RBAC behaviour is
unchanged.
"""
from __future__ import annotations

import json
import logging
import uuid as _uuid
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_org_id, get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.knowledge_base import service as kb_svc
from ai_portal.rag.answer.refusal import RefusalPolicy
from ai_portal.rag.answer.rewrite import ChatTurn
from ai_portal.rag.answer.service import (
    AnswerOptions,
    AnswerRequest,
    answer_stream,
)
from ai_portal.rag.search.federated import FederatedRequest, federated_search
from ai_portal.rag.search.hybrid import hybrid_search
from ai_portal.rag.search.types import SearchFilter, SearchRequest
from ai_portal.rag.search_providers import get_provider
from ai_portal.rag.search_providers.registry import UnknownSearchProvider

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["rag"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SearchFilterIn(BaseModel):
    sources: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    authors: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    date_from: str | None = None
    date_to: str | None = None

    def to_domain(self) -> SearchFilter:
        from datetime import datetime

        def _parse(s: str | None):
            if not s:
                return None
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00"))
            except ValueError:
                return None

        return SearchFilter(
            sources=tuple(self.sources),
            languages=tuple(self.languages),
            authors=tuple(self.authors),
            tags=tuple(self.tags),
            date_from=_parse(self.date_from),
            date_to=_parse(self.date_to),
        )


class SearchBody(BaseModel):
    query: str
    top_k: int = 10
    filter: SearchFilterIn = Field(default_factory=SearchFilterIn)
    rerank: bool = True


class SearchHitOut(BaseModel):
    chunk_id: str
    document_id: str
    kb_id: int
    text: str
    score: float
    meta: dict[str, Any] = Field(default_factory=dict)


class SearchOut(BaseModel):
    hits: list[SearchHitOut]


class AnswerOptionsIn(BaseModel):
    max_tokens: int = 800
    temperature: float = 0.2
    tone: str = "neutral"
    language: str | None = None
    answer_length: str = "medium"
    model: str = "gpt-4o-mini"


class ChatTurnIn(BaseModel):
    role: str
    text: str


class AnswerBody(BaseModel):
    query: str
    top_k: int = 8
    filter: SearchFilterIn = Field(default_factory=SearchFilterIn)
    prior_turns: list[ChatTurnIn] = Field(default_factory=list)
    options: AnswerOptionsIn = Field(default_factory=AnswerOptionsIn)
    min_score: float = 0.2


class FederatedAnswerBody(AnswerBody):
    kb_ids: list[int]


class SearchProviderBody(BaseModel):
    provider: str
    query: str
    num_results: int = 5
    options: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# /api/kbs/{id}/search
# ---------------------------------------------------------------------------


@router.post("/kbs/{kb_id}/search", response_model=SearchOut)
def search_kb(
    kb_id: int,
    body: SearchBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> SearchOut:
    kb_svc.get_owned_kb(db, user, kb_id)
    req = SearchRequest(
        query=body.query,
        kb_ids=[kb_id],
        top_k=body.top_k,
        filter=body.filter.to_domain(),
        actor_user_id=str(user.id),
        rerank=body.rerank,
    )
    hits = hybrid_search(db, req)
    return SearchOut(
        hits=[
            SearchHitOut(
                chunk_id=h.chunk_id,
                document_id=h.document_id,
                kb_id=h.kb_id,
                text=h.text,
                score=h.score,
                meta=h.meta or {},
            )
            for h in hits
        ]
    )


# ---------------------------------------------------------------------------
# /api/kbs/{id}/answer  (SSE)
# ---------------------------------------------------------------------------


def _sse_pack(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _stream_answer(db: Session, req: AnswerRequest):
    for ev in answer_stream(db, req):
        if ev.kind == "citation" and ev.citation is not None:
            yield _sse_pack("citation", asdict(ev.citation))
        elif ev.kind == "delta" and ev.text is not None:
            yield _sse_pack("delta", {"text": ev.text})
        elif ev.kind == "refusal":
            yield _sse_pack("refusal", {"text": ev.text or ""})
        elif ev.kind == "final" and ev.result is not None:
            res = ev.result
            yield _sse_pack(
                "final",
                {
                    "text": res.text,
                    "refused": res.refused,
                    "used_indices": res.used_indices,
                    "rewritten_query": res.rewritten_query,
                    "citations": [asdict(c) for c in res.citations],
                },
            )
    yield _sse_pack("done", {})


@router.post("/kbs/{kb_id}/answer")
def answer_kb(
    kb_id: int,
    body: AnswerBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
):
    kb_svc.get_owned_kb(db, user, kb_id)
    req = _build_answer_request(body, kb_ids=[kb_id], user=user, federated=False)
    return StreamingResponse(
        _stream_answer(db, req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/kbs/federated/answer")
def answer_federated(
    body: FederatedAnswerBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
):
    if not body.kb_ids:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="kb_ids required"
        )
    # Authorise every KB in the federation.
    for kid in body.kb_ids:
        kb_svc.get_owned_kb(db, user, kid)
    req = _build_answer_request(body, kb_ids=body.kb_ids, user=user, federated=True)
    return StreamingResponse(
        _stream_answer(db, req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _build_answer_request(
    body: AnswerBody, *, kb_ids: list[int], user: User, federated: bool
) -> AnswerRequest:
    opts = AnswerOptions(
        max_tokens=body.options.max_tokens,
        temperature=body.options.temperature,
        tone=body.options.tone,
        language=body.options.language,
        answer_length=body.options.answer_length,
        model=body.options.model,
    )
    return AnswerRequest(
        query=body.query,
        kb_ids=kb_ids,
        actor_user_id=str(user.id),
        prior_turns=[ChatTurn(role=t.role, text=t.text) for t in body.prior_turns],
        filter=body.filter.to_domain(),
        top_k=body.top_k,
        federated=federated,
        options=opts,
        refusal=RefusalPolicy(min_score=body.min_score),
    )


# ---------------------------------------------------------------------------
# /api/search (external + internal search providers)
# ---------------------------------------------------------------------------


@router.post("/search")
def search_via_provider(
    body: SearchProviderBody,
    user: User = Depends(get_current_user),
):
    # Deploy-vs-runtime: the provider must be declared + enabled in deployment
    # config. The UI can only pick among the declared set; an undeclared or
    # disabled provider is rejected here (never silently used).
    from ai_portal.rag import provider_config as pc

    cfg = pc.get_provider_config()
    if not cfg.layer(pc.SEARCH_PROVIDERS).is_selectable(body.provider):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=(
                f"search provider {body.provider!r} is not enabled in this "
                f"deployment (enabled: "
                f"{', '.join(cfg.layer(pc.SEARCH_PROVIDERS).enabled_ids())})"
            ),
        )
    try:
        provider = get_provider(body.provider, **body.options)
    except UnknownSearchProvider:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"unknown provider: {body.provider}"
        )
    try:
        results = provider.search(body.query, num_results=body.num_results)
    except Exception:  # noqa: BLE001
        log.exception("search provider failed: %s", body.provider)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="search provider failed"
        )
    return {
        "provider": body.provider,
        "results": [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet,
                "score": r.score,
                "published_date": r.published_date,
                "source": r.source,
            }
            for r in results
        ],
    }
