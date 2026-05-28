"""Read-time analytics aggregations for a knowledge base.

All aggregation lives here so it can be exercised by file-scoped tests that
just stage rows and assert the returned shape — no API layer required.
"""
from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_portal.knowledge_base.model import KbFeedback, KbQuery
from ai_portal.rag.analytics.cost import fetch_kb_cost_breakdown, to_out
from ai_portal.rag.analytics.schemas import (
    AnalyticsOverview,
    CitationHitRateOut,
    CostBreakdownOut,
    CostPoint,
    CostSeriesOut,
    FeedbackBreakdown,
    QueryLogIn,
    QueryStatOut,
)


@dataclass(slots=True)
class QueryStat:
    query: str
    count: int
    avg_hits: float
    avg_latency_ms: float


@dataclass(slots=True)
class CitationHitRate:
    document_id: str
    citations: int
    queries: int
    rate: float


@dataclass(slots=True)
class CostSeries:
    granularity: str
    points: list[CostPoint]
    total_cents: float


def _normalise(query: str) -> str:
    return " ".join((query or "").strip().lower().split())


def _bucket_day(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%d")


def compute_query_stats(rows: Iterable[KbQuery], *, limit: int = 10) -> list[QueryStat]:
    """Group queries by normalised text, return top-N by count."""
    by_key: dict[str, dict[str, float]] = {}
    for r in rows:
        key = _normalise(r.query)
        if not key:
            continue
        agg = by_key.setdefault(
            key,
            {"count": 0, "hits_sum": 0.0, "latency_sum": 0.0, "display": r.query},
        )
        agg["count"] += 1
        agg["hits_sum"] += r.hits_count or 0
        agg["latency_sum"] += r.latency_ms or 0
    stats: list[QueryStat] = []
    for k, agg in by_key.items():
        cnt = int(agg["count"])
        stats.append(
            QueryStat(
                query=str(agg.get("display", k)),
                count=cnt,
                avg_hits=agg["hits_sum"] / cnt if cnt else 0.0,
                avg_latency_ms=agg["latency_sum"] / cnt if cnt else 0.0,
            )
        )
    stats.sort(key=lambda s: s.count, reverse=True)
    return stats[:limit]


def compute_zero_result(rows: Iterable[KbQuery], *, limit: int = 10) -> list[QueryStat]:
    """Queries that returned no hits — feed the 'gap report'."""
    zero = [r for r in rows if (r.hits_count or 0) == 0]
    return compute_query_stats(zero, limit=limit)


def compute_citation_hit_rate(
    rows: Iterable[KbQuery], *, limit: int = 20
) -> list[CitationHitRate]:
    """For each cited document, how often it was cited vs total queries seen."""
    total_queries = 0
    by_doc: dict[str, int] = {}
    for r in rows:
        total_queries += 1
        for c in r.citations_json or []:
            doc_id = (c or {}).get("document_id")
            if doc_id:
                by_doc[doc_id] = by_doc.get(doc_id, 0) + 1
    out = [
        CitationHitRate(
            document_id=doc,
            citations=cnt,
            queries=total_queries,
            rate=(cnt / total_queries) if total_queries else 0.0,
        )
        for doc, cnt in by_doc.items()
    ]
    out.sort(key=lambda x: x.rate, reverse=True)
    return out[:limit]


def compute_feedback_breakdown(
    rows: Iterable[KbFeedback],
) -> FeedbackBreakdown:
    up = sum(1 for r in rows if (r.rating or "").lower() == "up")
    down = sum(1 for r in rows if (r.rating or "").lower() == "down")
    total = up + down
    ratio = (up / total) if total else 0.0
    return FeedbackBreakdown(up=up, down=down, ratio=ratio)


def compute_cost_series(
    rows: Iterable[KbQuery], *, granularity: str = "day"
) -> CostSeries:
    """Bucket cost + query count by day (UTC)."""
    points: dict[str, dict[str, float]] = {}
    total = 0.0
    for r in rows:
        ts = r.created_at or datetime.now(timezone.utc)
        bucket = _bucket_day(ts)
        agg = points.setdefault(bucket, {"cost_cents": 0.0, "queries": 0})
        agg["cost_cents"] += float(r.cost_cents or 0.0)
        agg["queries"] += 1
        total += float(r.cost_cents or 0.0)
    sorted_points = [
        CostPoint(
            bucket=b, cost_cents=v["cost_cents"], queries=int(v["queries"])
        )
        for b, v in sorted(points.items())
    ]
    return CostSeries(
        granularity=granularity, points=sorted_points, total_cents=total
    )


class KbAnalyticsService:
    """High-level entry point used by the HTTP layer."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def log_query(self, *, kb_id: int, payload: QueryLogIn) -> _uuid.UUID:
        row = KbQuery(
            kb_id=kb_id,
            user_id=payload.user_id,
            query=payload.query,
            hits_count=payload.hits_count,
            citations_json=payload.citations,
            latency_ms=payload.latency_ms,
            cost_cents=payload.cost_cents,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row.id

    def submit_feedback(
        self,
        *,
        kb_id: int,
        user_id: int | None,
        rating: str,
        query_id: _uuid.UUID | None = None,
        chunk_id: _uuid.UUID | None = None,
        comment: str | None = None,
    ) -> _uuid.UUID:
        row = KbFeedback(
            kb_id=kb_id,
            user_id=user_id,
            rating=rating,
            query_id=query_id,
            chunk_id=chunk_id,
            comment=comment,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row.id

    def overview(
        self,
        *,
        kb_id: int,
        window_days: int = 30,
        top_limit: int = 10,
    ) -> AnalyticsOverview:
        since = datetime.now(timezone.utc) - timedelta(days=window_days)
        q_rows = list(
            self.db.scalars(
                select(KbQuery).where(
                    KbQuery.kb_id == kb_id, KbQuery.created_at >= since
                )
            )
        )
        f_rows = list(
            self.db.scalars(
                select(KbFeedback).where(
                    KbFeedback.kb_id == kb_id, KbFeedback.created_at >= since
                )
            )
        )
        top = compute_query_stats(q_rows, limit=top_limit)
        zero = compute_zero_result(q_rows, limit=top_limit)
        cite = compute_citation_hit_rate(q_rows)
        fb = compute_feedback_breakdown(f_rows)
        cost = compute_cost_series(q_rows)
        breakdown = to_out(
            fetch_kb_cost_breakdown(self.db, kb_id=kb_id, since=since)
        )
        total_cost = float(
            self.db.scalar(
                select(func.coalesce(func.sum(KbQuery.cost_cents), 0.0)).where(
                    KbQuery.kb_id == kb_id, KbQuery.created_at >= since
                )
            )
            or 0.0
        )
        return AnalyticsOverview(
            top_queries=[
                QueryStatOut(
                    query=s.query,
                    count=s.count,
                    avg_hits=s.avg_hits,
                    avg_latency_ms=s.avg_latency_ms,
                )
                for s in top
            ],
            zero_result_queries=[
                QueryStatOut(
                    query=s.query,
                    count=s.count,
                    avg_hits=s.avg_hits,
                    avg_latency_ms=s.avg_latency_ms,
                )
                for s in zero
            ],
            citation_hit_rate=[
                CitationHitRateOut(
                    document_id=c.document_id,
                    citations=c.citations,
                    queries=c.queries,
                    rate=c.rate,
                )
                for c in cite
            ],
            feedback=fb,
            cost=CostSeriesOut(
                granularity=cost.granularity,
                points=cost.points,
                total_cents=cost.total_cents,
            ),
            cost_breakdown=breakdown,
            total_queries=len(q_rows),
            total_cost_cents=total_cost,
        )


__all__ = [
    "CitationHitRate",
    "CostSeries",
    "KbAnalyticsService",
    "QueryStat",
    "compute_citation_hit_rate",
    "compute_cost_series",
    "compute_feedback_breakdown",
    "compute_query_stats",
    "compute_zero_result",
]
