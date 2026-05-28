"""Lexical (BM25 / FTS) retrieval.

Production path uses Postgres FTS over ``DocumentChunk.search_vector``;
``ts_rank_cd`` gives us BM25-like behaviour without an extra index store.
A pure-Python ``rank_bm25`` fallback is also provided for in-memory tests.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable, Sequence

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.knowledge_base.model import Document, DocumentChunk
from ai_portal.rag.search.types import SearchHit

log = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def lexical_search(
    db: Session,
    *,
    query: str,
    kb_ids: list[int],
    top_k: int,
) -> list[SearchHit]:
    """Postgres FTS lexical search."""
    if not kb_ids or not query.strip():
        return []
    doc_ids = select(Document.id).where(
        Document.knowledge_base_id.in_(kb_ids),
        Document.status == "ready",
    )
    try:
        ts_query = sa_func.plainto_tsquery("english", query)
        stmt = (
            select(
                DocumentChunk,
                Document.knowledge_base_id,
                sa_func.ts_rank_cd(DocumentChunk.search_vector, ts_query).label("rank"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.document_id.in_(doc_ids),
                DocumentChunk.search_vector.is_not(None),
                DocumentChunk.search_vector.op("@@")(ts_query),
            )
            .order_by(sa_func.ts_rank_cd(DocumentChunk.search_vector, ts_query).desc())
            .limit(top_k)
        )
        rows = list(db.execute(stmt))
    except Exception:  # noqa: BLE001
        log.warning("FTS query failed", exc_info=True)
        return []

    hits: list[SearchHit] = []
    for rank, (chunk, kb_id, score) in enumerate(rows):
        meta = chunk.meta if isinstance(chunk.meta, dict) else {}
        hits.append(
            SearchHit(
                chunk_id=str(chunk.id),
                document_id=str(chunk.document_id),
                kb_id=int(kb_id),
                text=chunk.content or "",
                score=float(score or 0.0),
                meta=meta,
                lexical_rank=rank,
            )
        )
    return hits


def bm25_rank_in_memory(
    query: str, docs: Sequence[str], top_k: int = 10
) -> list[tuple[int, float]]:
    """Pure-Python BM25 used by tests and the search-providers internal backend.

    Returns ``[(orig_index, score), ...]`` sorted desc, length <= top_k.
    Falls back to bag-of-words intersection score when ``rank_bm25`` is not
    installed.
    """
    if not docs or not query.strip():
        return []
    tokenized_query = _tokenize(query)
    tokenized_docs = [_tokenize(d) for d in docs]
    try:
        from rank_bm25 import BM25Okapi  # type: ignore

        bm25 = BM25Okapi(tokenized_docs)
        scores = bm25.get_scores(tokenized_query)
    except Exception:  # noqa: BLE001 - lazy fallback
        scores = _fallback_overlap_scores(tokenized_query, tokenized_docs)
    ranked = sorted(enumerate(scores), key=lambda t: t[1], reverse=True)
    return [(i, float(s)) for i, s in ranked[:top_k] if s > 0]


def _fallback_overlap_scores(
    qtokens: list[str], dtokens: Iterable[list[str]]
) -> list[float]:
    qset = set(qtokens)
    return [float(sum(1 for t in d if t in qset)) for d in dtokens]
