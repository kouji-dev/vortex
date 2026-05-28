"""Routing protocol + dataclasses.

A *routing strategy* answers one question: given an :class:`LLMRequest` and a
list of candidate ``(provider, model)`` pairs, which one should this request
be sent to?

Strategies are stateless functions wrapped in a ``Protocol`` so tests can
substitute their own. Per-org configuration (priority order, weights,
custom rules) lives in :class:`RoutingPolicy.rules_json` and is passed to
the strategy via :class:`RoutingCtx`.

The candidate list is provided by the service layer — typically the set of
provider/model pairs the org has credentials for that satisfy the request's
``Capability`` requirements. Strategies must NOT do their own filtering by
capability; that is the service's job (capability_match is the one
exception — it filters by extra capabilities encoded in the policy rules).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from ai_portal.gateway.types import LLMRequest


@dataclass(frozen=True)
class ProviderModel:
    """One candidate route: a concrete provider + model pair.

    Fields beyond ``provider`` and ``model_id`` are optional and used by the
    cost/latency-aware strategies. The service populates them from the
    ``gateway_models`` catalog + recent telemetry.
    """

    provider: str
    model_id: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    price_input_per_1k_cents: float = 0.0
    price_output_per_1k_cents: float = 0.0
    price_cache_read_per_1k_cents: float = 0.0
    weight: float = 1.0
    # Recent observed p95 latency in milliseconds (None if unknown).
    p95_latency_ms: float | None = None
    healthy: bool = True
    # When the model was deprecated by its provider; ``None`` = still active.
    # Used by pin-date filtering (``model: "smart@2026-05-01"``).
    deprecated_at: datetime | None = None


@dataclass(frozen=True)
class RoutingCtx:
    """Per-request context handed to a strategy's :meth:`pick`.

    ``rules`` is the strategy-specific payload from
    :attr:`RoutingPolicy.rules_json`. Each strategy documents the schema it
    expects (see individual strategy modules).
    """

    rules: dict[str, Any] = field(default_factory=dict)
    # Recent telemetry by ``(provider, model_id)`` → p95 latency ms.
    metrics: dict[tuple[str, str], float] = field(default_factory=dict)
    # Random seed (tests pin this; production passes ``None``).
    seed: int | None = None


class RoutingError(Exception):
    """Raised when no candidate satisfies the policy."""


@runtime_checkable
class RoutingStrategy(Protocol):
    """One pick-a-route policy.

    Implementations are typically singletons — pass the same instance to
    every request. State (telemetry, weights) is supplied via the policy's
    ``rules_json`` and the request's :class:`RoutingCtx`.
    """

    name: str

    def pick(
        self,
        req: LLMRequest,
        candidates: list[ProviderModel],
        ctx: RoutingCtx,
    ) -> ProviderModel:
        """Return the chosen candidate. Raise :class:`RoutingError` on empty."""
        ...


__all__ = [
    "ProviderModel",
    "RoutingCtx",
    "RoutingError",
    "RoutingStrategy",
]
