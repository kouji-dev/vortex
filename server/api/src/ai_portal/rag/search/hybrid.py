"""Hybrid search: BM25 + dense + filters fused via RRF, optional rerank.

Flow:
    1. Embed query (gateway-routed via voyage embed provider).
    2. Dense top-N from pgvector.
    3. Lexical top-N from Postgres FTS.
    4. Fuse via Reciprocal Rank Fusion (k=60).
    5. Apply metadata filters (source / language / date / tag / author).
    6. Apply freshness + source-priority boosts.
    7. Optional rerank pass via Gateway facade.
    8. Truncate to top_k.
"""
from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy.orm import Session

from ai_portal.rag.search.boosts import apply_boosts
from ai_portal.rag.search.dense import dense_search, embed_query
from ai_portal.rag.search.filters import apply_filter
from ai_portal.rag.search.lexical import lexical_search
from ai_portal.rag.search.rerank import rerank_hits
from ai_portal.rag.search.rrf import reciprocal_rank_fusion
from ai_portal.rag.search.types import SearchHit, SearchRequest

log = logging.getLogger(__name__)

# Over-fetch from each retriever; RRF + rerank then trims.
DEFAULT_RETRIEVE_K = 30


def hybrid_search(
    db: Session,
    req: SearchRequest,
    *,
    retrieve_k: int = DEFAULT_RETRIEVE_K,
    query_embedding: Sequence[float] | None = None,
) -> list[SearchHit]:
    """Run hybrid retrieval for a single search request."""
    if not req.kb_ids:
        return []

    qe = list(query_embedding) if query_embedding is not None else embed_query(req.query)

    dense = dense_search(db, query_embedding=qe, kb_ids=req.kb_ids, top_k=retrieve_k)
    lex = lexical_search(db, query=req.query, kb_ids=req.kb_ids, top_k=retrieve_k)

    return _fuse_filter_boost_rerank(req, dense, lex)


def _fuse_filter_boost_rerank(
    req: SearchRequest,
    dense: list[SearchHit],
    lex: list[SearchHit],
) -> list[SearchHit]:
    """Pure-Python tail of the pipeline — directly testable."""
    by_id: dict[str, SearchHit] = {}
    for h in dense:
        by_id[h.chunk_id] = h
    for h in lex:
        if h.chunk_id in by_id:
            existing = by_id[h.chunk_id]
            existing.lexical_rank = h.lexical_rank
        else:
            by_id[h.chunk_id] = h

    fused = reciprocal_rank_fusion(
        [h.chunk_id for h in dense],
        [h.chunk_id for h in lex],
    )

    ordered: list[SearchHit] = []
    for rank, (cid, score) in enumerate(fused):
        hit = by_id.get(cid)
        if hit is None:
            continue
        ordered.append(
            SearchHit(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                kb_id=hit.kb_id,
                text=hit.text,
                score=score,
                meta=dict(hit.meta or {}),
                lexical_rank=hit.lexical_rank,
                dense_rank=hit.dense_rank,
            )
        )

    filtered = apply_filter(ordered, req.filter)
    boosted = apply_boosts(
        filtered,
        freshness=req.boost_freshness,
        source_weights=req.boost_source_priority or None,
    )

    if req.rerank and boosted:
        boosted = rerank_hits(req.query, boosted, top_k=max(req.top_k, len(boosted)))

    return boosted[: req.top_k]
