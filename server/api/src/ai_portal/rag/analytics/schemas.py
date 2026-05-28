"""Pydantic schemas for the KB analytics HTTP surface."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class QueryStatOut(BaseModel):
    query: str
    count: int
    avg_hits: float = 0.0
    avg_latency_ms: float = 0.0


class CitationHitRateOut(BaseModel):
    document_id: str
    citations: int
    queries: int
    rate: float


class FeedbackBreakdown(BaseModel):
    up: int = 0
    down: int = 0
    ratio: float = 0.0


class CostPoint(BaseModel):
    bucket: str  # day or hour
    cost_cents: float = 0.0
    queries: int = 0


class CostSeriesOut(BaseModel):
    granularity: str = "day"
    points: list[CostPoint] = Field(default_factory=list)
    total_cents: float = 0.0


class AnalyticsOverview(BaseModel):
    """Top-level dashboard payload."""

    top_queries: list[QueryStatOut] = Field(default_factory=list)
    zero_result_queries: list[QueryStatOut] = Field(default_factory=list)
    citation_hit_rate: list[CitationHitRateOut] = Field(default_factory=list)
    feedback: FeedbackBreakdown = Field(default_factory=FeedbackBreakdown)
    cost: CostSeriesOut = Field(default_factory=CostSeriesOut)
    total_queries: int = 0
    total_cost_cents: float = 0.0


class FeedbackIn(BaseModel):
    rating: str  # "up" | "down"
    query_id: str | None = None
    chunk_id: str | None = None
    comment: str | None = None


class QueryLogIn(BaseModel):
    """Internal: log one retrieval/answer event for analytics rollups."""

    query: str
    hits_count: int = 0
    citations: list[dict] = Field(default_factory=list)
    latency_ms: int = 0
    cost_cents: float = 0.0
    user_id: int | None = None
    created_at: datetime | None = None


__all__ = [
    "AnalyticsOverview",
    "CitationHitRateOut",
    "CostPoint",
    "CostSeriesOut",
    "FeedbackBreakdown",
    "FeedbackIn",
    "QueryLogIn",
    "QueryStatOut",
]
