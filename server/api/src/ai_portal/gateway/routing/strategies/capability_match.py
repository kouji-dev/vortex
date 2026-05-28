"""Capability-match strategy — filter by required capabilities then pick.

Rules shape:

.. code-block:: json

    {"require": ["vision", "tools"], "tie_breaker": "cost"}

``tie_breaker`` selects among the qualifying set. Supported values:

- ``"first"`` (default) — the first qualifier in candidate order.
- ``"cost"`` — cheapest qualifier (input+output).
- ``"latency"`` — lowest known p95 latency.
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


class CapabilityMatchStrategy(RoutingStrategy):
    name = "capability_match"

    def pick(
        self,
        req: LLMRequest,
        candidates: list[ProviderModel],
        ctx: RoutingCtx,
    ) -> ProviderModel:
        if not candidates:
            raise RoutingError("no candidates")
        required = set(ctx.rules.get("require") or [])
        qualifiers = [
            c for c in candidates if c.healthy and required.issubset(c.capabilities)
        ]
        if not qualifiers:
            raise RoutingError(f"no candidate matches required capabilities {required}")
        tie = ctx.rules.get("tie_breaker", "first")
        if tie == "cost":
            return min(
                qualifiers,
                key=lambda c: c.price_input_per_1k_cents + c.price_output_per_1k_cents,
            )
        if tie == "latency":
            return min(
                qualifiers,
                key=lambda c: (
                    c.p95_latency_ms if c.p95_latency_ms is not None else math.inf
                ),
            )
        return qualifiers[0]
