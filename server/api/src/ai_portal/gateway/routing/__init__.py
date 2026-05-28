"""Gateway routing — strategies, policies, aliases, failover, circuit breaker.

Phase C of the Gateway plan. Surfaces:

- :class:`RoutingPolicy`, :class:`ModelAlias` — ORM models for per-org config.
- :class:`RoutingStrategy` protocol + 7 bundled strategies.
- :class:`Failover` + :class:`CircuitBreaker` — resilience layer over a
  strategy's pick.
- :class:`RoutingService` — resolves alias → policy → strategy.pick →
  provider invocation; honors the ``x-gateway-routing-policy`` header.
"""
from __future__ import annotations

from ai_portal.gateway.routing.model import ModelAlias, RoutingPolicy
from ai_portal.gateway.routing.protocol import (
    ProviderModel,
    RoutingCtx,
    RoutingStrategy,
)
from ai_portal.gateway.routing.registry import STRATEGY_REGISTRY, get_strategy

__all__ = [
    "ModelAlias",
    "ProviderModel",
    "RoutingCtx",
    "RoutingPolicy",
    "RoutingStrategy",
    "STRATEGY_REGISTRY",
    "get_strategy",
]
