"""Priority strategy — first healthy candidate in the configured order.

Rules shape:

.. code-block:: json

    {"order": [
        {"provider": "anthropic", "model_id": "claude-sonnet-4-6"},
        {"provider": "openai",    "model_id": "gpt-4o"}
    ]}

Walks ``order`` top-to-bottom and returns the first match that is healthy
and present in ``candidates``. Falls back to the first candidate when the
order is empty / no entry matched.
"""
from __future__ import annotations

from ai_portal.gateway.routing.protocol import (
    ProviderModel,
    RoutingCtx,
    RoutingError,
    RoutingStrategy,
)
from ai_portal.gateway.types import LLMRequest


class PriorityStrategy(RoutingStrategy):
    name = "priority"

    def pick(
        self,
        req: LLMRequest,
        candidates: list[ProviderModel],
        ctx: RoutingCtx,
    ) -> ProviderModel:
        if not candidates:
            raise RoutingError("no candidates")
        order = ctx.rules.get("order") or []
        by_key = {(c.provider, c.model_id): c for c in candidates}
        for entry in order:
            key = (entry.get("provider"), entry.get("model_id"))
            match = by_key.get(key)
            if match is not None and match.healthy:
                return match
        # Fallback: first healthy candidate.
        for c in candidates:
            if c.healthy:
                return c
        raise RoutingError("all candidates unhealthy")
