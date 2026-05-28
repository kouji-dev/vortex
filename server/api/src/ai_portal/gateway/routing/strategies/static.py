"""Static strategy — always pick the configured ``(provider, model_id)``.

Rules shape:

.. code-block:: json

    {"provider": "openai", "model_id": "gpt-4o"}

Raises :class:`RoutingError` if the target isn't in the candidate list.
"""
from __future__ import annotations

from ai_portal.gateway.routing.protocol import (
    ProviderModel,
    RoutingCtx,
    RoutingError,
    RoutingStrategy,
)
from ai_portal.gateway.types import LLMRequest


class StaticStrategy(RoutingStrategy):
    name = "static"

    def pick(
        self,
        req: LLMRequest,
        candidates: list[ProviderModel],
        ctx: RoutingCtx,
    ) -> ProviderModel:
        if not candidates:
            raise RoutingError("no candidates")
        target_provider = ctx.rules.get("provider")
        target_model = ctx.rules.get("model_id")
        if not target_provider or not target_model:
            # Default: first candidate.
            return candidates[0]
        for c in candidates:
            if c.provider == target_provider and c.model_id == target_model:
                return c
        raise RoutingError(
            f"static target {target_provider}/{target_model} not in candidates"
        )
