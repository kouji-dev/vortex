"""Weighted strategy — sample a candidate using per-candidate weights.

Rules shape (optional):

.. code-block:: json

    {"weights": {"openai:gpt-4o": 2.0, "anthropic:claude-sonnet-4-6": 1.0}}

When ``rules.weights`` is absent the strategy uses each candidate's
``weight`` attribute. Weight 0 (or negative) disables that candidate.
"""

from __future__ import annotations

import random
from typing import Any

from ai_portal.gateway.routing.protocol import (
    ProviderModel,
    RoutingCtx,
    RoutingError,
    RoutingStrategy,
)
from ai_portal.gateway.types import LLMRequest


def _candidate_weight(c: ProviderModel, weights: dict[str, Any] | None) -> float:
    if weights is not None:
        # Explicit ``weights`` dict from rules_json — entries not present are 0
        # (caller has opted into precise control).
        key = f"{c.provider}:{c.model_id}"
        return max(0.0, float(weights.get(key, 0.0)))
    return max(0.0, float(c.weight))


class WeightedStrategy(RoutingStrategy):
    name = "weighted"

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
        weights_rule = ctx.rules.get("weights")
        weights = [_candidate_weight(c, weights_rule) for c in healthy]
        total = sum(weights)
        if total <= 0:
            return healthy[0]
        rng = random.Random(ctx.seed)
        roll = rng.random() * total
        acc = 0.0
        for c, w in zip(healthy, weights, strict=False):
            acc += w
            if roll <= acc:
                return c
        return healthy[-1]
