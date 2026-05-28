"""Latency-optimized strategy — pick the lowest observed p95 latency.

Lookup order per candidate:

1. ``ctx.metrics[(provider, model_id)]`` — live telemetry from the router.
2. ``candidate.p95_latency_ms`` — last-known catalog snapshot.
3. ``+inf`` — unknown latencies are sorted last.

If every candidate is unknown the first healthy one is returned.
"""
from __future__ import annotations

import math

from ai_portal.gateway.routing.protocol import (
    ProviderModel,
    RoutingCtx,
    RoutingError,
    RoutingStrategy,
)
from ai_portal.gateway.types import LLMRequest


def _latency(c: ProviderModel, ctx: RoutingCtx) -> float:
    live = ctx.metrics.get((c.provider, c.model_id))
    if live is not None:
        return float(live)
    if c.p95_latency_ms is not None:
        return float(c.p95_latency_ms)
    return math.inf


class LatencyOptimizedStrategy(RoutingStrategy):
    name = "latency_optimized"

    def pick(
        self,
        req: LLMRequest,
        candidates: list[ProviderModel],
        ctx: RoutingCtx,
    ) -> ProviderModel:
        if not candidates:
            raise RoutingError("no candidates")
        healthy = [c for c in candidates if c.healthy]
        if not healthy:
            raise RoutingError("all candidates unhealthy")
        return min(healthy, key=lambda c: _latency(c, ctx))
