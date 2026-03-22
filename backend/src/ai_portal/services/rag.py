from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.models import Document, DocumentChunk


def retrieve_context(
    db: Session,
    *,
    assistant_id: int,
    query_embedding: list[float],
    top_k: int = 5,
) -> str:
    """Return concatenated chunk text for assistant-scoped similarity search."""
    doc_ids = select(Document.id).where(
        Document.assistant_id == assistant_id,
        Document.status == "ready",
    )
    stmt = (
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id.in_(doc_ids),
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
        .limit(top_k)
    )
    chunks = list(db.scalars(stmt))
    if not chunks:
        return ""
    return "\n\n".join(c.content for c in chunks)
