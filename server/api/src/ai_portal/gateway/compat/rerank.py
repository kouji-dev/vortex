"""POST /v1/rerank — Cohere-shaped rerank endpoint.

Wire shape (request)::

    POST /v1/rerank
    {
      "query": "...",
      "documents": ["doc-1", "doc-2", ...],
      "model": "rerank-2",            # optional — provider default if absent
      "top_n": N,                     # optional — return only top N
      "return_documents": false       # optional — echo doc text in result
    }

Response::

    {
      "id": "...",
      "results": [
        {"index": int, "relevance_score": float,
         "document": {"text": "..."}? }
      ],
      "meta": {"api_version": {"version": "1"}}
    }

Backend selection (which Reranker is used) is wired via
:func:`get_reranker` which can be overridden in tests / DI containers.
The default implementation picks the first configured provider in this
priority: Voyage, Cohere, BGE.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ai_portal.control_plane.deps import require_actor
from ai_portal.core.config import get_settings
from ai_portal.gateway.rerank import Reranker, RerankResult
from ai_portal.rbac.service import Actor

router = APIRouter(tags=["gateway-rerank"])


# ── schemas ──────────────────────────────────────────────────────────────


class RerankRequest(BaseModel):
    query: str = Field(min_length=1)
    documents: list[str] = Field(min_length=1)
    model: str | None = None
    top_n: int | None = Field(default=None, ge=1)
    return_documents: bool = False


class _ResultDocument(BaseModel):
    text: str


class RerankResultOut(BaseModel):
    index: int
    relevance_score: float
    document: _ResultDocument | None = None


class _Meta(BaseModel):
    api_version: dict = Field(default_factory=lambda: {"version": "1"})


class RerankResponse(BaseModel):
    id: str
    results: list[RerankResultOut]
    meta: _Meta = Field(default_factory=_Meta)


# ── reranker DI ──────────────────────────────────────────────────────────


def get_reranker() -> Reranker:
    """Choose a reranker based on settings.

    Override this dep in tests / DI containers to inject a stub. Real
    callers will use the first configured of: Voyage → Cohere → BGE.
    """
    s = get_settings()
    if getattr(s, "voyage_api_key", "").strip():
        from ai_portal.gateway.rerank.providers.voyage import VoyageReranker

        return VoyageReranker(api_key=s.voyage_api_key)
    cohere_key = getattr(s, "cohere_api_key", "")
    if isinstance(cohere_key, str) and cohere_key.strip():
        from ai_portal.gateway.rerank.providers.cohere import CohereReranker

        return CohereReranker(api_key=cohere_key)
    bge_url = getattr(s, "bge_reranker_url", "")
    if isinstance(bge_url, str) and bge_url.strip():
        from ai_portal.gateway.rerank.providers.bge import BgeReranker

        return BgeReranker(
            base_url=bge_url,
            api_key=getattr(s, "bge_reranker_api_key", None) or None,
        )
    raise HTTPException(
        status_code=503,
        detail="no rerank provider configured (set VOYAGE_API_KEY, COHERE_API_KEY, or BGE_RERANKER_URL)",
    )


# ── route ────────────────────────────────────────────────────────────────


def _to_out(r: RerankResult) -> RerankResultOut:
    return RerankResultOut(
        index=r.index,
        relevance_score=r.relevance_score,
        document=_ResultDocument(text=r.document) if r.document is not None else None,
    )


@router.post("/v1/rerank", response_model=RerankResponse)
async def rerank(
    body: RerankRequest,
    actor: Annotated[Actor, Depends(require_actor)],
    reranker: Annotated[Reranker, Depends(get_reranker)],
) -> RerankResponse:
    """Cohere-compatible rerank surface."""
    results = await reranker.rerank(
        query=body.query,
        documents=body.documents,
        top_k=body.top_n,
        model=body.model,
        return_documents=body.return_documents,
    )
    return RerankResponse(
        id=str(uuid.uuid4()),
        results=[_to_out(r) for r in results],
    )


__all__ = ["router", "get_reranker", "RerankRequest", "RerankResponse"]
