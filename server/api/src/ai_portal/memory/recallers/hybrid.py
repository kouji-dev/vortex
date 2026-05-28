"""hybrid recaller — vector + BM25 + recency + importance blend.

Pulls a candidate pool (3x top_k) from pgvector, computes BM25 over the
candidate texts (when ``rank-bm25`` is available; otherwise a deterministic
token-overlap fallback is used so the recaller remains usable in CI), and
combines the four signals with the weights from ``RecallOpts``.
"""
from __future__ import annotations

import logging
import math
import re
import time
import uuid
from collections import Counter
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.gateway import Actor, embed as gw_embed
from ai_portal.memory.repository import MemoryRepo

from .protocol import RecallOpts, RecallScope, Recalled
from .registry import register

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised when dep present
    from rank_bm25 import BM25Okapi  # type: ignore

    BM25_AVAILABLE = True
except Exception:
    BM25Okapi = None  # type: ignore
    BM25_AVAILABLE = False


_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _WORD_RE.findall(text or "")]


def _bm25_scores(query_tokens: list[str], docs: list[list[str]]) -> list[float]:
    if not docs:
        return []
    if BM25_AVAILABLE:
        bm = BM25Okapi(docs)
        return list(bm.get_scores(query_tokens))
    # Fallback: simple log-weighted overlap.
    df_counter: Counter[str] = Counter()
    for d in docs:
        for tok in set(d):
            df_counter[tok] += 1
    scores: list[float] = []
    n = len(docs)
    for d in docs:
        tf = Counter(d)
        s = 0.0
        for tok in query_tokens:
            if tok in tf:
                idf = math.log(1 + (n / (1 + df_counter[tok])))
                s += tf[tok] * idf
        scores.append(s)
    return scores


def _norm(vals: list[float]) -> list[float]:
    if not vals:
        return []
    mx = max(vals)
    if mx <= 0:
        return [0.0] * len(vals)
    return [v / mx for v in vals]


def _recency(last_used_at, created_at, now: float) -> float:
    ts = last_used_at or created_at
    if ts is None:
        return 0.0
    age_d = max(0.0, (now - ts.timestamp()) / 86400.0)
    return math.exp(-age_d / 30.0)


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


class HybridRecaller:
    name = "hybrid"

    def __init__(
        self,
        session: AsyncSession,
        *,
        embedding_model: str = "text-embedding-3-small",
    ):
        self.session = session
        self.repo = MemoryRepo(session)
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
        org_uuid = uuid.UUID(scope.org_id) if isinstance(scope.org_id, str) else scope.org_id
        rows = await self.repo.vector_search(
            org_id=org_uuid, embedding=embedding, limit=max(opts.top_k * 3, opts.top_k)
        )
        if not rows:
            return []

        q_tokens = _tokenize(query)
        docs_tokens = [_tokenize(m.text) for m, _ in rows]
        bm25_raw = _bm25_scores(q_tokens, docs_tokens)
        bm25_norm = _norm(bm25_raw)

        now = time.time()
        alpha = opts.bm25_weight if opts.bm25_weight else 0.2
        beta = opts.recency_weight
        gamma = opts.importance_weight
        vec_w = max(0.0, 1.0 - alpha - beta - gamma)

        scored: list[Recalled] = []
        for (m, dist), bm in zip(rows, bm25_norm, strict=True):
            vec_score = max(0.0, 1.0 - dist)
            rec = _recency(m.last_used_at, m.created_at, now)
            imp = float(m.importance or 0.0)
            score = vec_w * vec_score + alpha * bm + beta * rec + gamma * imp
            scored.append(
                Recalled(
                    memory_id=str(m.id),
                    text=m.text,
                    score=score,
                    explain={
                        "vector": vec_score,
                        "bm25": bm,
                        "recency": rec,
                        "importance": imp,
                        "why": "vector+bm25+recency+importance",
                    },
                )
            )
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[: opts.top_k]


def make_hybrid(
    session: AsyncSession,
    *,
    embedding_model: str = "text-embedding-3-small",
) -> HybridRecaller:
    return HybridRecaller(session, embedding_model=embedding_model)


class _HybridSentinel:
    name = "hybrid"
    bm25_available = BM25_AVAILABLE

    async def recall(self, query, scope, opts):  # pragma: no cover
        raise RuntimeError("hybrid requires a session; use make_hybrid(session)")


register(_HybridSentinel())
