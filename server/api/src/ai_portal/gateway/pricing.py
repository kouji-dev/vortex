"""Per-request cost calculation.

Cost cents = (tokens_in / 1k * price_in) + (tokens_out / 1k * price_out)
+ (tokens_cache_read / 1k * price_cache_read).

Pricing is snapshotted from :class:`ai_portal.catalog.model.GatewayModel` at
request time so later catalog edits do not retroactively change trace cost.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_portal.gateway.types import Usage


@dataclass(frozen=True, slots=True)
class PricingSnapshot:
    """Frozen pricing slice extracted from a :class:`GatewayModel` row.

    All rates are integer cents per 1_000 tokens. ``0`` means free.
    """

    price_input_per_1k_cents: int = 0
    price_output_per_1k_cents: int = 0
    price_cache_read_per_1k_cents: int = 0

    @classmethod
    def from_gateway_model(cls, model: object) -> PricingSnapshot:
        """Build a snapshot from a :class:`GatewayModel`-like object.

        Accepts any object exposing the three pricing fields. Falls back to
        zero rates when fields are missing (e.g., in-memory stubs in tests).
        """
        return cls(
            price_input_per_1k_cents=int(
                getattr(model, "price_input_per_1k_cents", 0) or 0
            ),
            price_output_per_1k_cents=int(
                getattr(model, "price_output_per_1k_cents", 0) or 0
            ),
            price_cache_read_per_1k_cents=int(
                getattr(model, "price_cache_read_per_1k_cents", 0) or 0
            ),
        )


def compute_cost_cents(usage: Usage, pricing: PricingSnapshot) -> float:
    """Compute the cost (in cents) for one LLM call.

    Cache *write* tokens are charged at the full input rate (Anthropic billing
    model). Cache *read* tokens are charged at the dedicated cache-read rate
    so callers get the prompt-cache discount.
    """
    cost = 0.0
    cost += (usage.input_tokens / 1000.0) * pricing.price_input_per_1k_cents
    cost += (usage.output_tokens / 1000.0) * pricing.price_output_per_1k_cents
    cost += (
        usage.cache_read_tokens / 1000.0
    ) * pricing.price_cache_read_per_1k_cents
    cost += (
        usage.cache_write_tokens / 1000.0
    ) * pricing.price_input_per_1k_cents
    return round(cost, 6)


__all__ = [
    "PricingSnapshot",
    "compute_cost_cents",
]
