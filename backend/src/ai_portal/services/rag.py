from __future__ import annotations

import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.models import Document, DocumentChunk
from ai_portal.models.knowledge_base import KnowledgeBase


def _embedding_to_list(v: Any) -> list[float]:
    """Normalize DB/driver vectors (list, tuple, numpy ndarray, etc.) to floats."""
    if v is None:
        return []
    if hasattr(v, "tolist") and callable(getattr(v, "tolist")) and not isinstance(
        v, (str, bytes, bytearray)
    ):
        raw = v.tolist()
        if isinstance(raw, list):
            return [float(x) for x in raw]
        return [float(raw)]
    return [float(x) for x in v]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = math.fsum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(math.fsum(x * x for x in a))
    nb = math.sqrt(math.fsum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _cosine_score(chunk: DocumentChunk, query_embedding: list[float]) -> float:
    """Similarity score for metadata (matches pgvector ordering: higher = closer)."""
    emb = chunk.embedding
    if emb is None:
        return 0.0
    # Loaded rows are often list or numpy.ndarray; .cosine_distance exists on pgvector
    # SQL constructs, not on materialized Python values.
    if hasattr(emb, "cosine_distance") and callable(getattr(emb, "cosine_distance", None)):
        try:
            dist = emb.cosine_distance(query_embedding)
            return round(max(0.0, 1.0 - float(dist)), 4)
        except (TypeError, ValueError, ZeroDivisionError, AttributeError):
            pass
    try:
        vec = _embedding_to_list(emb)
        q = _embedding_to_list(query_embedding)
        sim = _cosine_similarity(vec, q)
        return round(max(0.0, sim), 4)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def retrieve_context_with_meta(
    db: Session,
    *,
    knowledge_base_ids: list[int],
    query_embedding: list[float],
    top_k: int = 5,
) -> tuple[str, list[dict]]:
    """
    Run KB-scoped similarity search.

    Returns:
        (context_text, used_kbs_meta)

    where used_kbs_meta is a list of dicts:
        [{"kb_id": int, "kb_name": str, "chunks_used": int, "top_score": float, "sections": list[str]}]
    """
    if not knowledge_base_ids:
        return "", []

    doc_ids = select(Document.id).where(
        Document.knowledge_base_id.in_(knowledge_base_ids),
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
        return "", []

    # Map document_id → knowledge_base_id
    doc_id_to_kb: dict[int, int] = {}
    for doc in db.scalars(
        select(Document).where(Document.id.in_([c.document_id for c in chunks]))
    ).all():
        doc_id_to_kb[doc.id] = doc.knowledge_base_id

    # Fetch KB names for the contributing KBs
    contributing_kb_ids = list({doc_id_to_kb[c.document_id] for c in chunks if c.document_id in doc_id_to_kb})
    kb_name_map: dict[int, str] = {}
    for kb in db.scalars(
        select(KnowledgeBase).where(KnowledgeBase.id.in_(contributing_kb_ids))
    ).all():
        kb_name_map[kb.id] = kb.name

    # Group chunks by KB
    kb_chunks: dict[int, list[DocumentChunk]] = {}
    for chunk in chunks:
        kb_id = doc_id_to_kb.get(chunk.document_id)
        if kb_id is not None:
            kb_chunks.setdefault(kb_id, []).append(chunk)

    # Build metadata list
    used_kbs_meta: list[dict] = []
    for kb_id, kb_chunk_list in kb_chunks.items():
        scores = [_cosine_score(c, query_embedding) for c in kb_chunk_list]
        sections_seen: set[str] = set()
        sections: list[str] = []
        for c in kb_chunk_list:
            if isinstance(c.meta, dict):
                src = c.meta.get("source") or c.meta.get("page") or c.meta.get("section")
                if src and str(src) not in sections_seen:
                    sections_seen.add(str(src))
                    sections.append(str(src))
        used_kbs_meta.append(
            {
                "kb_id": kb_id,
                "kb_name": kb_name_map.get(kb_id, f"KB {kb_id}"),
                "chunks_used": len(kb_chunk_list),
                "top_score": max(scores) if scores else 0.0,
                "sections": sections,
            }
        )

    context = "\n\n".join(c.content for c in chunks)
    return context, used_kbs_meta


def retrieve_context(
    db: Session,
    *,
    knowledge_base_ids: list[int],
    query_embedding: list[float],
    top_k: int = 5,
) -> str:
    """Backward-compatible wrapper — returns context string only."""
    context, _ = retrieve_context_with_meta(
        db, knowledge_base_ids=knowledge_base_ids, query_embedding=query_embedding, top_k=top_k
    )
    return context
