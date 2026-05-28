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

from ai_portal.gateway.routing.circuit_breaker import (
    CircuitBreaker,
    CircuitOpen,
    CircuitState,
)
from ai_portal.gateway.routing.failover import (
    Failover,
    FailoverExhausted,
    ProviderHTTPError,
    ProviderTimeoutError,
)
from ai_portal.gateway.routing.model import ModelAlias, RoutingPolicy
from ai_portal.gateway.routing.protocol import (
    ProviderModel,
    RoutingCtx,
    RoutingError,
    RoutingStrategy,
)
from ai_portal.gateway.routing.registry import STRATEGY_REGISTRY, get_strategy
from ai_portal.gateway.routing.service import (
    ROUTING_POLICY_HEADER,
    RoutingResolution,
    RoutingService,
    extract_policy_override,
)

__all__ = [
    "CircuitBreaker",
    "CircuitOpen",
    "CircuitState",
    "Failover",
    "FailoverExhausted",
    "ModelAlias",
    "ProviderHTTPError",
    "ProviderModel",
    "ProviderTimeoutError",
    "ROUTING_POLICY_HEADER",
    "RoutingCtx",
    "RoutingError",
    "RoutingPolicy",
    "RoutingResolution",
    "RoutingService",
    "RoutingStrategy",
    "STRATEGY_REGISTRY",
    "extract_policy_override",
    "get_strategy",
]
