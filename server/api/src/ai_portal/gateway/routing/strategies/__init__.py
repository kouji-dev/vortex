"""Bundled routing strategies (Phase C1)."""
from __future__ import annotations

from ai_portal.gateway.routing.strategies.capability_match import (
    CapabilityMatchStrategy,
)
from ai_portal.gateway.routing.strategies.cost_optimized import (
    CostOptimizedStrategy,
)
from ai_portal.gateway.routing.strategies.custom_rules import CustomRulesStrategy
from ai_portal.gateway.routing.strategies.latency_optimized import (
    LatencyOptimizedStrategy,
)
from ai_portal.gateway.routing.strategies.priority import PriorityStrategy
from ai_portal.gateway.routing.strategies.static import StaticStrategy
from ai_portal.gateway.routing.strategies.weighted import WeightedStrategy

__all__ = [
    "CapabilityMatchStrategy",
    "CostOptimizedStrategy",
    "CustomRulesStrategy",
    "LatencyOptimizedStrategy",
    "PriorityStrategy",
    "StaticStrategy",
    "WeightedStrategy",
]
