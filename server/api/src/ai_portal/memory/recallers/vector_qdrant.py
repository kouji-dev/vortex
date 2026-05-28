"""vector_qdrant recaller — optional, requires ``qdrant-client``.

Mirrors :class:`VectorPgvectorRecaller` but talks to a Qdrant collection.
``qdrant-client`` is intentionally an optional dependency: the recaller is
registered as a sentinel and instantiated via :func:`make_vector_qdrant`
only when the dependency is present.
"""
from __future__ import annotations

import logging
import math
import time
import uuid
from typing import Any, Callable

from ai_portal.gateway import Actor, embed as gw_embed

from .protocol import RecallOpts, RecallScope, Recalled
from .registry import register

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised when dep present
    from qdrant_client import AsyncQdrantClient  # type: ignore
    from qdrant_client.http import models as qmodels  # type: ignore

    QDRANT_AVAILABLE = True
except Exception:  # pragma: no cover
    AsyncQdrantClient = None  # type: ignore
    qmodels = None  # type: ignore
    QDRANT_AVAILABLE = False


def _scope_actor(scope: RecallScope) -> Actor:
    try:
        org_uuid = uuid.UUID(scope.org_id)
    except Exception:
        org_uuid = uuid.uuid4()
    try:
        uid = int(scope.actor_user_id)
    except Exception:
        uid = None
    return Actor(org_id=org_uuid, user_id=uid, kind="service")


ACTOR_FACTORY: Callable[[RecallScope], Actor] = _scope_actor


def _recency_score(last_used_at: float | None, created_at: float, now: float) -> float:
    ts = last_used_at if last_used_at is not None else created_at
    age_d = max(0.0, (now - ts) / 86400.0)
    return math.exp(-age_d / 30.0)


class VectorQdrantRecaller:
    name = "vector_qdrant"

    def __init__(
        self,
        client: Any,
        *,
        collection: str = "memories",
        embedding_model: str = "text-embedding-3-small",
    ):
        if not QDRANT_AVAILABLE:
            raise RuntimeError("qdrant-client not installed")
        self.client = client
        self.collection = collection
        self.embedding_model = embedding_model

    async def _embed(self, query: str, scope: RecallScope) -> list[float]:
        actor = ACTOR_FACTORY(scope)
        emb = await gw_embed([query], model=self.embedding_model, actor=actor)
        data = getattr(emb, "data", None) or []
        return list(data[0]) if data else []

    async def recall(
        self,
        query: str,
        scope: RecallScope,
        opts: RecallOpts,
    ) -> list[Recalled]:
        embedding = await self._embed(query, scope)
        if not embedding:
            return []
        hits = await self.client.search(
            collection_name=self.collection,
            query_vector=embedding,
            limit=max(opts.top_k * 3, opts.top_k),
            query_filter=qmodels.Filter(  # type: ignore[union-attr]
                must=[
                    qmodels.FieldCondition(
                        key="org_id",
                        match=qmodels.MatchValue(value=str(scope.org_id)),
                    )
                ]
            ),
        )
        now = time.time()
        vec_w = max(0.0, 1.0 - opts.recency_weight - opts.importance_weight)
        results: list[Recalled] = []
        for hit in hits:
            payload = getattr(hit, "payload", {}) or {}
            text = payload.get("text", "")
            importance = float(payload.get("importance", 0.5) or 0.0)
            last_used = payload.get("last_used_at_epoch")
            created = float(payload.get("created_at_epoch", now))
            rec = _recency_score(last_used, created, now)
            vec_score = float(getattr(hit, "score", 0.0) or 0.0)
            score = (
                vec_w * vec_score + opts.recency_weight * rec + opts.importance_weight * importance
            )
            results.append(
                Recalled(
                    memory_id=str(payload.get("memory_id") or hit.id),
                    text=text,
                    score=score,
                    explain={
                        "vector": vec_score,
                        "recency": rec,
                        "importance": importance,
                        "why": "qdrant cosine + recency + importance",
                    },
                )
            )
        results.sort(key=lambda r: r.score, reverse=True)
        return results[: opts.top_k]


def make_vector_qdrant(client: Any, **kw: Any) -> VectorQdrantRecaller:
    return VectorQdrantRecaller(client, **kw)


class _QdrantSentinel:
    name = "vector_qdrant"
    available = QDRANT_AVAILABLE

    async def recall(self, query, scope, opts):  # pragma: no cover
        raise RuntimeError(
            "vector_qdrant requires qdrant-client + a configured client; "
            "use make_vector_qdrant(client)"
        )


register(_QdrantSentinel())
