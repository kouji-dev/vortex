"""Strategy registry — name → singleton instance.

The :class:`RoutingPolicy.strategy` column stores the string name; the
service uses :func:`get_strategy` to resolve it at request time.
"""

from __future__ import annotations

from ai_portal.gateway.routing.protocol import RoutingStrategy
from ai_portal.gateway.routing.strategies import (
    CapabilityMatchStrategy,
    CostOptimizedStrategy,
    CustomRulesStrategy,
    LatencyOptimizedStrategy,
    PriorityStrategy,
    StaticStrategy,
    WeightedStrategy,
)

STRATEGY_REGISTRY: dict[str, RoutingStrategy] = {
    "static": StaticStrategy(),
    "priority": PriorityStrategy(),
    "weighted": WeightedStrategy(),
    "cost_optimized": CostOptimizedStrategy(),
    "latency_optimized": LatencyOptimizedStrategy(),
    "capability_match": CapabilityMatchStrategy(),
    "custom_rules": CustomRulesStrategy(),
}


def get_strategy(name: str) -> RoutingStrategy:
    """Return the bundled strategy for *name*.

    :raises KeyError: if *name* is not registered.
    """
    try:
        return STRATEGY_REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"unknown routing strategy {name!r}; known: {sorted(STRATEGY_REGISTRY)}"
        ) from exc


__all__ = ["STRATEGY_REGISTRY", "get_strategy"]
