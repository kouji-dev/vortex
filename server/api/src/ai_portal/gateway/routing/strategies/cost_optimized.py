"""Cost-optimized strategy — pick the cheapest candidate.

Effective cost = ``price_input × input_weight + price_output × output_weight``.
By default input_output_ratio = ``[1.0, 3.0]`` (output dominates as in
typical chat workloads).

Rules shape (optional):

.. code-block:: json

    {"input_output_ratio": [1.0, 5.0]}
"""

from __future__ import annotations

from ai_portal.gateway.routing.protocol import (
    ProviderModel,
    RoutingCtx,
    RoutingError,
    RoutingStrategy,
)
from ai_portal.gateway.types import LLMRequest


def _score(c: ProviderModel, ratio: tuple[float, float]) -> float:
    return (
        c.price_input_per_1k_cents * ratio[0] + c.price_output_per_1k_cents * ratio[1]
    )


class CostOptimizedStrategy(RoutingStrategy):
    name = "cost_optimized"

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
        raw_ratio = ctx.rules.get("input_output_ratio") or [1.0, 3.0]
        ratio = (float(raw_ratio[0]), float(raw_ratio[1]))
        return min(healthy, key=lambda c: _score(c, ratio))
