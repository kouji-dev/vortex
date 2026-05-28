"""Rerank pass for retrieved hits.

Routes through the Gateway facade (`gateway.rerank`) when available; falls
back to the existing Voyage client and finally to a cosine-similarity
shim. Pure-Python so callers can monkey-patch the rerank fn in tests.
"""
from __future__ import annotations

import logging
from typing import Callable

from ai_portal.rag.search.types import SearchHit

log = logging.getLogger(__name__)

# Default rerank model id (Voyage-Rerank-2, per spec).
DEFAULT_RERANK_MODEL = "rerank-2"

RerankFn = Callable[[str, list[str], str, int], list[tuple[int, float]]]
"""Callable: (query, docs, model, top_k) -> [(orig_index, score), ...] sorted desc."""


def _gateway_rerank(
    query: str, docs: list[str], model: str, top_k: int
) -> list[tuple[int, float]]:
    """Try the Gateway facade first; degrade to Voyage SDK then identity."""
    # Preferred: ai_portal.gateway.rerank when present.
    try:  # pragma: no cover - gateway facade is added in another wave
        from ai_portal.gateway import rerank as gw_rerank  # type: ignore

        result = gw_rerank(query=query, documents=docs, model=model, top_k=top_k)
        return [(r.index, float(r.relevance_score)) for r in result.results]
    except Exception:  # noqa: BLE001
        pass

    # Direct Voyage fallback (existing infra in this repo).
    try:
        import voyageai  # type: ignore

        from ai_portal.core.config import get_settings

        settings = get_settings()
        key = (settings.voyage_api_key or "").strip()
        if not key:
            raise RuntimeError("no voyage api key")
        client = voyageai.Client(api_key=key)
        rr = client.rerank(query, docs, model=model, top_k=top_k)
        return [(r.index, float(r.relevance_score)) for r in rr.results]
    except Exception:  # noqa: BLE001
        log.debug("rerank: no gateway/voyage available; falling back to identity")

    # Identity fallback — keep input order.
    return [(i, 1.0 / (i + 1)) for i in range(min(top_k, len(docs)))]


def rerank_hits(
    query: str,
    hits: list[SearchHit],
    *,
    top_k: int,
    model: str = DEFAULT_RERANK_MODEL,
    rerank_fn: RerankFn | None = None,
) -> list[SearchHit]:
    """Apply a rerank pass and return the top-k re-scored hits."""
    if not hits:
        return []
    docs = [h.text for h in hits]
    fn = rerank_fn or _gateway_rerank
    try:
        ranked = fn(query, docs, model, top_k)
    except Exception:  # noqa: BLE001
        log.warning("rerank failed; returning original order", exc_info=True)
        return hits[:top_k]

    out: list[SearchHit] = []
    for idx, score in ranked[:top_k]:
        if 0 <= idx < len(hits):
            h = hits[idx]
            out.append(
                SearchHit(
                    chunk_id=h.chunk_id,
                    document_id=h.document_id,
                    kb_id=h.kb_id,
                    text=h.text,
                    score=float(score),
                    meta=dict(h.meta or {}),
                    lexical_rank=h.lexical_rank,
                    dense_rank=h.dense_rank,
                    rerank_score=float(score),
                )
            )
    return out
