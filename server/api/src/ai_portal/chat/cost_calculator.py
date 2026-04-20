"""Isolated cost calculator for LLM calls, tool calls, and server-side tools."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ai_portal.chat.llm_pricing import get_llm_rates
from ai_portal.chat.tool_outcome import ToolCallOutcome
from ai_portal.chat.tool_pricing import get_tool_flat_rate


CostSource = Literal[
    "flat_rate", "provider_metered", "unknown_model", "free",
]


class CostResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    cost_usd: Decimal
    estimated: bool
    source: CostSource


_ZERO = Decimal("0")
_MILLION = Decimal("1000000")


def _rate_component(tokens: int, rate_per_million: Decimal | None) -> Decimal:
    if rate_per_million is None or tokens <= 0:
        return _ZERO
    return (Decimal(tokens) * rate_per_million) / _MILLION


def compute_llm_cost(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int,
    cache_creation_input_tokens: int,
    reasoning_tokens: int,
) -> CostResult:
    rates = get_llm_rates(model)
    if rates is None:
        return CostResult(cost_usd=_ZERO, estimated=True, source="unknown_model")

    billable_input = max(input_tokens - cached_input_tokens - cache_creation_input_tokens, 0)

    total = (
        _rate_component(billable_input, rates.input_per_million)
        + _rate_component(cached_input_tokens, rates.cached_input_per_million or rates.input_per_million)
        + _rate_component(cache_creation_input_tokens, rates.cache_creation_per_million or rates.input_per_million)
        + _rate_component(output_tokens, rates.output_per_million)
        + _rate_component(reasoning_tokens, rates.reasoning_per_million or rates.output_per_million)
    )
    return CostResult(cost_usd=total.quantize(Decimal("0.000001")), estimated=False, source="flat_rate")


def compute_tool_cost(outcome: ToolCallOutcome) -> CostResult:
    if outcome.cost_usd is not None:
        return CostResult(cost_usd=outcome.cost_usd, estimated=False, source="provider_metered")
    flat = get_tool_flat_rate(outcome.provider)
    if flat is None:
        return CostResult(cost_usd=_ZERO, estimated=True, source="unknown_model")
    if flat == _ZERO:
        return CostResult(cost_usd=_ZERO, estimated=False, source="free")
    return CostResult(cost_usd=flat, estimated=True, source="flat_rate")


def compute_server_tool_cost(
    *,
    tool_name: str,
    provider: str,
    usage_metadata: dict | None,
) -> CostResult:
    if usage_metadata and "cost_usd" in usage_metadata:
        value = usage_metadata["cost_usd"]
        return CostResult(cost_usd=Decimal(str(value)), estimated=False, source="provider_metered")
    return CostResult(cost_usd=_ZERO, estimated=False, source="free")
