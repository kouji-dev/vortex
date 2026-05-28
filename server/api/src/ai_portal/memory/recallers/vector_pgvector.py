"""vector_pgvector recaller — pgvector cosine + recency + importance blend.

The recaller is *not* a singleton — it needs a SQLAlchemy session, so the
registered name maps to a factory ``make_vector_pgvector(session)`` that
returns a fresh instance.
"""
from __future__ import annotations

import logging
import math
import time
import uuid
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.gateway import Actor, embed as gw_embed
from ai_portal.memory.repository import MemoryRepo

from .protocol import RecallOpts, RecallScope, Recalled
from .registry import register

logger = logging.getLogger(__name__)


def _recency_score(last_used_at, created_at, now: float) -> float:
    ts = last_used_at or created_at
    if ts is None:
        return 0.0
    age_days = max(0.0, (now - ts.timestamp()) / 86400.0)
    return math.exp(-age_days / 30.0)


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


# Production code may override.
ACTOR_FACTORY: Callable[[RecallScope], Actor] = _scope_actor


class VectorPgvectorRecaller:
    name = "vector_pgvector"

    def __init__(self, session: AsyncSession, *, embedding_model: str = "text-embedding-3-small"):
        self.session = session
        self.repo = MemoryRepo(session)
        self.embedding_model = embedding_model

    async def _embed(self, query: str, scope: RecallScope) -> list[float]:
        actor = ACTOR_FACTORY(scope)
        emb = await gw_embed([query], model=self.embedding_model, actor=actor)
        # canonical Embeddings exposes .data[0] (list[float])
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
        org_uuid = uuid.UUID(scope.org_id) if isinstance(scope.org_id, str) else scope.org_id
        rows = await self.repo.vector_search(
            org_id=org_uuid, embedding=embedding, limit=max(opts.top_k * 3, opts.top_k)
        )
        now = time.time()
        vec_w = max(0.0, 1.0 - opts.recency_weight - opts.importance_weight)
        results: list[Recalled] = []
        for m, dist in rows:
            vec_score = max(0.0, 1.0 - dist)
            rec = _recency_score(m.last_used_at, m.created_at, now)
            score = (
                vec_w * vec_score
                + opts.recency_weight * rec
                + opts.importance_weight * float(m.importance or 0.0)
            )
            results.append(
                Recalled(
                    memory_id=str(m.id),
                    text=m.text,
                    score=score,
                    explain={
                        "vector": vec_score,
                        "recency": rec,
                        "importance": float(m.importance or 0.0),
                        "why": "vector cosine + recency + importance",
                    },
                )
            )
        results.sort(key=lambda r: r.score, reverse=True)
        return results[: opts.top_k]


def make_vector_pgvector(
    session: AsyncSession,
    *,
    embedding_model: str = "text-embedding-3-small",
) -> VectorPgvectorRecaller:
    return VectorPgvectorRecaller(session, embedding_model=embedding_model)


# Sentinel registration so name resolution sees the recaller class. Callers
# that need a session-bound instance use ``make_vector_pgvector(session)``.
class _PgvectorSentinel:
    name = "vector_pgvector"

    async def recall(self, query, scope, opts):  # pragma: no cover - unused
        raise RuntimeError(
            "vector_pgvector requires a session; use make_vector_pgvector(session)"
        )


register(_PgvectorSentinel())
