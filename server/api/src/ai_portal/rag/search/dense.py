"""Dense (vector) retrieval — pgvector cosine over ``DocumentChunk``.

The query is embedded via the existing rag embedding provider (which in turn
will route through the Gateway once available); the heavy similarity work
runs in Postgres via pgvector's ``cosine_distance``.
"""
from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.knowledge_base.model import Document, DocumentChunk
from ai_portal.rag.search.types import SearchHit

log = logging.getLogger(__name__)


def embed_query(text: str) -> list[float]:
    """Embed a query using the project's embedding provider (gateway-routed)."""
    from ai_portal.rag.providers import voyage as embedding_svc

    return embedding_svc.embed_texts([text], input_type="query")[0]


def dense_search(
    db: Session,
    *,
    query_embedding: Sequence[float],
    kb_ids: list[int],
    top_k: int,
) -> list[SearchHit]:
    """Return the top-k chunks across the given KBs by vector similarity."""
    if not kb_ids or not query_embedding:
        return []
    qe = list(query_embedding)
    doc_ids = select(Document.id).where(
        Document.knowledge_base_id.in_(kb_ids),
        Document.status == "ready",
    )
    stmt = (
        select(DocumentChunk, Document.knowledge_base_id)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.document_id.in_(doc_ids),
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(DocumentChunk.embedding.cosine_distance(qe))
        .limit(top_k)
    )
    rows = list(db.execute(stmt))
    hits: list[SearchHit] = []
    for rank, (chunk, kb_id) in enumerate(rows):
        meta = chunk.meta if isinstance(chunk.meta, dict) else {}
        hits.append(
            SearchHit(
                chunk_id=str(chunk.id),
                document_id=str(chunk.document_id),
                kb_id=int(kb_id),
                text=chunk.content or "",
                score=1.0 / (rank + 1),  # rank-based placeholder
                meta=meta,
                dense_rank=rank,
            )
        )
    return hits
