from __future__ import annotations

import logging
import math
from typing import Any

import voyageai
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.config import get_settings
from ai_portal.models import Document, DocumentChunk
from ai_portal.models.knowledge_base import KnowledgeBase
from ai_portal.services import embedding as embedding_svc

log = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Hybrid search helpers
# ---------------------------------------------------------------------------


def _rrf_merge(
    vector_ids: list[int],
    bm25_ids: list[int],
    k: int = 60,
) -> list[int]:
    """Reciprocal Rank Fusion over two ranked ID lists.

    score(id) = 1/(k + rank_vector) + 1/(k + rank_bm25)
    Ranks are 1-based; IDs absent from a list contribute 0 for that component.
    """
    scores: dict[int, float] = {}
    for rank, cid in enumerate(vector_ids, start=1):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    for rank, cid in enumerate(bm25_ids, start=1):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=scores.__getitem__, reverse=True)


def _rerank_chunks(
    query: str,
    chunks: list[DocumentChunk],
    query_embedding: list[float],
    top_k: int,
    *,
    settings: Any = None,
) -> list[tuple[DocumentChunk, float]]:
    """Re-rank chunks using Voyage Rerank when available, else cosine fallback."""
    if not chunks:
        return []

    settings = settings or get_settings()

    if settings.voyage_api_key.strip():
        try:
            client = voyageai.Client(api_key=settings.voyage_api_key)
            docs = [c.content for c in chunks]
            rr = client.rerank(query, docs, model="rerank-2", top_k=top_k)
            return [(chunks[r.index], r.relevance_score) for r in rr.results]
        except Exception:
            log.warning("Voyage rerank failed, falling back to cosine", exc_info=True)

    scored = [(_cosine_score(c, query_embedding), c) for c in chunks]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [(c, s) for s, c in scored[:top_k]]


def _source_attribution(chunk: DocumentChunk, doc_filename: str) -> str:
    """Build a source attribution string for a chunk."""
    meta = chunk.meta if isinstance(chunk.meta, dict) else {}
    page = meta.get("page")
    section = meta.get("section") or meta.get("source", "")
    parts = [f"Source: {doc_filename}"]
    if page is not None:
        parts.append(f"page {page}")
    if section:
        parts.append(f'section "{section}"')
    return "[" + ", ".join(parts) + "]"


def search_knowledge_base_tool(
    db: Session,
    *,
    query: str,
    kb_ids: list[int],
    top_k: int | None = None,
) -> dict[str, Any]:
    """Main RAG entry point for the agent tool loop.

    1. Embed query
    2. pgvector cosine search → max_top_k candidates
    3. BM25 (tsvector/tsquery) → max_top_k candidates
    4. RRF merge
    5. Voyage Rerank → min_top_k final chunks
    6. Filter by similarity threshold
    7. Build context + source attribution + citations

    Returns ``{"context": str, "used_kbs": list, "citations": list}``.
    """
    if not kb_ids:
        return {"context": "", "used_kbs": [], "citations": []}

    settings = get_settings()
    max_top_k = settings.rag_max_top_k
    min_top_k = top_k or settings.rag_min_top_k
    threshold = settings.rag_similarity_threshold

    # -- 1. Embed query --
    query_embedding = embedding_svc.embed_texts([query], input_type="query")[0]

    # Subquery: ready docs in these KBs
    doc_ids_sq = select(Document.id).where(
        Document.knowledge_base_id.in_(kb_ids),
        Document.status == "ready",
    )

    # -- 2. pgvector cosine search --
    vec_stmt = (
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id.in_(doc_ids_sq),
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
        .limit(max_top_k)
    )
    vector_chunks: list[DocumentChunk] = list(db.scalars(vec_stmt))
    vector_id_list = [c.id for c in vector_chunks]

    # -- 3. BM25 full-text search --
    bm25_id_list: list[int] = []
    bm25_chunk_map: dict[int, DocumentChunk] = {}
    try:
        ts_query = sa_func.plainto_tsquery("english", query)
        bm25_stmt = (
            select(DocumentChunk)
            .where(
                DocumentChunk.document_id.in_(doc_ids_sq),
                DocumentChunk.search_vector.is_not(None),
                DocumentChunk.search_vector.op("@@")(ts_query),
            )
            .order_by(
                sa_func.ts_rank_cd(DocumentChunk.search_vector, ts_query).desc()
            )
            .limit(max_top_k)
        )
        bm25_chunks: list[DocumentChunk] = list(db.scalars(bm25_stmt))
        bm25_id_list = [c.id for c in bm25_chunks]
        bm25_chunk_map = {c.id: c for c in bm25_chunks}
    except Exception:
        log.warning("BM25 search failed; continuing with vector-only", exc_info=True)

    # -- 4. RRF merge --
    merged_ids = _rrf_merge(vector_id_list, bm25_id_list)

    # Collect chunk objects in merged order
    chunk_by_id: dict[int, DocumentChunk] = {c.id: c for c in vector_chunks}
    chunk_by_id.update(bm25_chunk_map)
    merged_chunks = [chunk_by_id[cid] for cid in merged_ids if cid in chunk_by_id]

    if not merged_chunks:
        return {"context": "", "used_kbs": [], "citations": []}

    # -- 5. Rerank --
    reranked = _rerank_chunks(
        query, merged_chunks, query_embedding, top_k=min_top_k, settings=settings
    )

    # -- 6. Threshold filter --
    final = [(c, score) for c, score in reranked if score >= threshold]
    if not final:
        return {"context": "", "used_kbs": [], "citations": []}

    final_chunks = [c for c, _ in final]

    # -- 7. Build context, attributions, metadata --
    doc_ids_needed = list({c.document_id for c in final_chunks})
    doc_map: dict[int, Document] = {}
    for doc in db.scalars(select(Document).where(Document.id.in_(doc_ids_needed))).all():
        doc_map[doc.id] = doc

    kb_id_set: set[int] = set()
    citations: list[dict] = []
    context_parts: list[str] = []

    for chunk, score in final:
        doc = doc_map.get(chunk.document_id)
        filename = doc.filename if doc else "unknown"
        kb_id = doc.knowledge_base_id if doc else None
        if kb_id is not None:
            kb_id_set.add(kb_id)

        attribution = _source_attribution(chunk, filename)
        context_parts.append(f"{chunk.content}\n{attribution}")
        meta = chunk.meta if isinstance(chunk.meta, dict) else {}
        citations.append({
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "filename": filename,
            "page": meta.get("page"),
            "section": meta.get("section") or meta.get("source", ""),
            "score": round(score, 4),
        })

    # KB-level metadata
    used_kbs: list[dict] = []
    if kb_id_set:
        kb_name_map: dict[int, str] = {}
        for kb in db.scalars(
            select(KnowledgeBase).where(KnowledgeBase.id.in_(list(kb_id_set)))
        ).all():
            kb_name_map[kb.id] = kb.name

        kb_chunks: dict[int, list[tuple[DocumentChunk, float]]] = {}
        for chunk, score in final:
            doc = doc_map.get(chunk.document_id)
            if doc:
                kb_chunks.setdefault(doc.knowledge_base_id, []).append((chunk, score))

        for kb_id, pairs in kb_chunks.items():
            used_kbs.append({
                "kb_id": kb_id,
                "kb_name": kb_name_map.get(kb_id, f"KB {kb_id}"),
                "chunks_used": len(pairs),
                "top_score": round(max(s for _, s in pairs), 4),
            })

    context = "\n\n".join(context_parts)
    return {"context": context, "used_kbs": used_kbs, "citations": citations}
