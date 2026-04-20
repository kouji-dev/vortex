"""LLM model pricing table for the chat domain.

Prices are in USD per 1M tokens. Update this dict when provider pricing changes;
historical cost values keep their original computed value.

Sources (checked 2026-04-19):
  Anthropic: https://www.anthropic.com/pricing
  Google: https://ai.google.dev/pricing
  OpenAI: https://openai.com/api/pricing
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class LlmRate:
    input_per_million: Decimal
    output_per_million: Decimal
    cached_input_per_million: Decimal | None = None
    cache_creation_per_million: Decimal | None = None
    reasoning_per_million: Decimal | None = None


_RATES: dict[str, LlmRate] = {
    # Anthropic Claude 4.x
    "claude-opus-4-7": LlmRate(
        input_per_million=Decimal("15.0"),
        output_per_million=Decimal("75.0"),
        cached_input_per_million=Decimal("1.5"),
        cache_creation_per_million=Decimal("18.75"),
    ),
    "claude-opus-4-6": LlmRate(
        input_per_million=Decimal("15.0"),
        output_per_million=Decimal("75.0"),
        cached_input_per_million=Decimal("1.5"),
        cache_creation_per_million=Decimal("18.75"),
    ),
    "claude-opus-4-5-20251101": LlmRate(
        input_per_million=Decimal("15.0"),
        output_per_million=Decimal("75.0"),
        cached_input_per_million=Decimal("1.5"),
        cache_creation_per_million=Decimal("18.75"),
    ),
    "claude-sonnet-4-6": LlmRate(
        input_per_million=Decimal("3.0"),
        output_per_million=Decimal("15.0"),
        cached_input_per_million=Decimal("0.30"),
        cache_creation_per_million=Decimal("3.75"),
    ),
    "claude-sonnet-4-5-20250929": LlmRate(
        input_per_million=Decimal("3.0"),
        output_per_million=Decimal("15.0"),
        cached_input_per_million=Decimal("0.30"),
        cache_creation_per_million=Decimal("3.75"),
    ),
    "claude-haiku-4-5": LlmRate(
        input_per_million=Decimal("0.80"),
        output_per_million=Decimal("4.0"),
        cached_input_per_million=Decimal("0.08"),
        cache_creation_per_million=Decimal("1.0"),
    ),
    "claude-haiku-4-5-20251001": LlmRate(
        input_per_million=Decimal("0.80"),
        output_per_million=Decimal("4.0"),
        cached_input_per_million=Decimal("0.08"),
        cache_creation_per_million=Decimal("1.0"),
    ),

    # Google Gemini 2.x
    "gemini-2.5-pro-preview-05-06": LlmRate(
        input_per_million=Decimal("1.25"),
        output_per_million=Decimal("10.0"),
        cached_input_per_million=Decimal("0.31"),
        cache_creation_per_million=Decimal("1.5625"),
    ),
    "gemini-2.5-flash": LlmRate(
        input_per_million=Decimal("0.15"),
        output_per_million=Decimal("0.60"),
        cached_input_per_million=Decimal("0.0375"),
        cache_creation_per_million=Decimal("0.1875"),
    ),
    "gemini-2.5-flash-lite": LlmRate(
        input_per_million=Decimal("0.075"),
        output_per_million=Decimal("0.30"),
        cached_input_per_million=Decimal("0.01875"),
        cache_creation_per_million=Decimal("0.09375"),
    ),
    "gemini-2.0-flash": LlmRate(
        input_per_million=Decimal("0.10"),
        output_per_million=Decimal("0.40"),
        cached_input_per_million=Decimal("0.025"),
        cache_creation_per_million=Decimal("0.125"),
    ),
    "gemini-2.0-flash-lite": LlmRate(
        input_per_million=Decimal("0.075"),
        output_per_million=Decimal("0.30"),
        cached_input_per_million=Decimal("0.01875"),
        cache_creation_per_million=Decimal("0.09375"),
    ),

    # OpenAI o-series and GPT-4o
    "o3": LlmRate(
        input_per_million=Decimal("10.0"),
        output_per_million=Decimal("40.0"),
        cached_input_per_million=Decimal("2.5"),
        cache_creation_per_million=Decimal("12.5"),
    ),
    "o3-mini": LlmRate(
        input_per_million=Decimal("1.1"),
        output_per_million=Decimal("4.4"),
        cached_input_per_million=Decimal("0.55"),
        cache_creation_per_million=Decimal("1.375"),
    ),
    "o4-mini": LlmRate(
        input_per_million=Decimal("1.1"),
        output_per_million=Decimal("4.4"),
        cached_input_per_million=Decimal("0.275"),
        cache_creation_per_million=Decimal("1.375"),
    ),
    "gpt-4o": LlmRate(
        input_per_million=Decimal("2.5"),
        output_per_million=Decimal("10.0"),
        cached_input_per_million=Decimal("1.25"),
        cache_creation_per_million=Decimal("3.125"),
    ),
    "gpt-4o-mini": LlmRate(
        input_per_million=Decimal("0.15"),
        output_per_million=Decimal("0.60"),
        cached_input_per_million=Decimal("0.075"),
        cache_creation_per_million=Decimal("0.1875"),
    ),
}


def get_llm_rates(model: str) -> LlmRate | None:
    return _RATES.get(model)
