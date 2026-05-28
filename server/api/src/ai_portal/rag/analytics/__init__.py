"""KB analytics — top queries, zero-result (gap report), citation hit-rate,
feedback (thumbs up/down), cost dashboard.

Pure aggregation over ``kb_queries`` + ``kb_feedback`` + control-plane
``usage_events`` (joined module="rag"). Rollups are computed on read for v1
to avoid an extra worker; the protocol is stable so a background rollup can
be swapped in later.
"""
from ai_portal.rag.analytics.rollups import (
    CitationHitRate,
    CostSeries,
    KbAnalyticsService,
    QueryStat,
)
from ai_portal.rag.analytics.schemas import AnalyticsOverview, FeedbackIn

__all__ = [
    "AnalyticsOverview",
    "CitationHitRate",
    "CostSeries",
    "FeedbackIn",
    "KbAnalyticsService",
    "QueryStat",
]
