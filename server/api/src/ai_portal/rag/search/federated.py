"""Federated multi-KB search.

Spec: fans out to N KBs, normalises per-KB scores, fuses globally via RRF,
optional global rerank.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ai_portal.rag.search.hybrid import DEFAULT_RETRIEVE_K, hybrid_search
from ai_portal.rag.search.rerank import rerank_hits
from ai_portal.rag.search.rrf import reciprocal_rank_fusion
from ai_portal.rag.search.types import SearchFilter, SearchHit

log = logging.getLogger(__name__)


@dataclass
class FederatedRequest:
    query: str
    kb_ids: list[int]
    top_k: int = 10
    per_kb_top_k: int = 10
    filter: SearchFilter = field(default_factory=SearchFilter)
    rerank: bool = True


def federated_search(db: Session, req: FederatedRequest) -> list[SearchHit]:
    """Run independent hybrid searches per KB and fuse globally."""
    if not req.kb_ids:
        return []

    # 1. Per-KB hybrid retrieval. Inside one KB we want over-fetch.
    per_kb_hits: dict[int, list[SearchHit]] = {}
    for kb_id in req.kb_ids:
        from ai_portal.rag.search.types import SearchRequest

        sub = SearchRequest(
            query=req.query,
            kb_ids=[kb_id],
            top_k=req.per_kb_top_k,
            filter=req.filter,
            rerank=False,  # defer rerank to global pass
        )
        hits = hybrid_search(db, sub, retrieve_k=DEFAULT_RETRIEVE_K)
        per_kb_hits[kb_id] = hits

    # 2. Global RRF fuse — each KB's ordered chunk_id list is a system.
    ranked_lists = [[h.chunk_id for h in hits] for hits in per_kb_hits.values()]
    fused = reciprocal_rank_fusion(*ranked_lists)

    # 3. Stitch fused order back to SearchHit objects.
    by_id: dict[str, SearchHit] = {}
    for hits in per_kb_hits.values():
        for h in hits:
            by_id[h.chunk_id] = h

    merged: list[SearchHit] = []
    for cid, score in fused:
        h = by_id.get(cid)
        if h is None:
            continue
        merged.append(
            SearchHit(
                chunk_id=h.chunk_id,
                document_id=h.document_id,
                kb_id=h.kb_id,
                text=h.text,
                score=score,
                meta=dict(h.meta or {}),
                lexical_rank=h.lexical_rank,
                dense_rank=h.dense_rank,
            )
        )

    # 4. Global rerank.
    if req.rerank and merged:
        merged = rerank_hits(req.query, merged, top_k=max(req.top_k, len(merged)))

    return merged[: req.top_k]
