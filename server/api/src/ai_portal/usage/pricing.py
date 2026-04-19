"""Per-model cost computation.

Prices are in USD per 1M tokens. Update this dict when provider pricing changes;
historical ``message_usage.cost_usd`` rows keep their original computed value.

Sources (checked 2026-04-19):
  Anthropic: https://www.anthropic.com/pricing
  Google: https://ai.google.dev/pricing
  OpenAI: https://openai.com/api/pricing
"""

from __future__ import annotations

from decimal import Decimal

# (input_per_1m, output_per_1m, cached_read_per_1m)
# cached_read is typically 10% of input; cache_creation is typically 125% of input.
_PRICES: dict[str, tuple[Decimal, Decimal, Decimal]] = {
    # Anthropic Claude 4.x
    "claude-opus-4-7": (Decimal("15.0"), Decimal("75.0"), Decimal("1.5")),
    "claude-opus-4-6": (Decimal("15.0"), Decimal("75.0"), Decimal("1.5")),
    "claude-opus-4-5-20251101": (Decimal("15.0"), Decimal("75.0"), Decimal("1.5")),
    "claude-sonnet-4-6": (Decimal("3.0"), Decimal("15.0"), Decimal("0.30")),
    "claude-sonnet-4-5-20250929": (Decimal("3.0"), Decimal("15.0"), Decimal("0.30")),
    "claude-haiku-4-5": (Decimal("0.80"), Decimal("4.0"), Decimal("0.08")),
    "claude-haiku-4-5-20251001": (Decimal("0.80"), Decimal("4.0"), Decimal("0.08")),

    # Google Gemini 2.x
    "gemini-2.5-pro-preview-05-06": (Decimal("1.25"), Decimal("10.0"), Decimal("0.31")),
    "gemini-2.5-flash": (Decimal("0.15"), Decimal("0.60"), Decimal("0.0375")),
    "gemini-2.5-flash-lite": (Decimal("0.075"), Decimal("0.30"), Decimal("0.01875")),
    "gemini-2.0-flash": (Decimal("0.10"), Decimal("0.40"), Decimal("0.025")),
    "gemini-2.0-flash-lite": (Decimal("0.075"), Decimal("0.30"), Decimal("0.01875")),

    # OpenAI o-series
    "o3": (Decimal("10.0"), Decimal("40.0"), Decimal("2.5")),
    "o3-mini": (Decimal("1.1"), Decimal("4.4"), Decimal("0.55")),
    "o4-mini": (Decimal("1.1"), Decimal("4.4"), Decimal("0.275")),
    "gpt-4o": (Decimal("2.5"), Decimal("10.0"), Decimal("1.25")),
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60"), Decimal("0.075")),
}

# Multiplier for cache_creation relative to input price (typically 1.25×).
_CACHE_CREATION_MULTIPLIER = Decimal("1.25")


def compute_cost_usd(
    api_model_id: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> Decimal:
    """Return cost in USD for one LLM call.

    Falls back to $0 for unknown models so metering never crashes a chat reply.
    """
    model = (api_model_id or "").strip().lower()
    # Strip provider prefix if any (e.g. "anthropic-claude-haiku-4-5" → "claude-haiku-4-5").
    for pfx in ("anthropic-", "google-gemini-", "openai-"):
        if model.startswith(pfx):
            model = model[len(pfx):]
            break

    prices = _PRICES.get(model)
    if prices is None:
        # Try prefix match for version variants (e.g. "gemini-2.5-flash-xxx").
        for key, val in _PRICES.items():
            if model.startswith(key):
                prices = val
                break

    if prices is None:
        return Decimal("0")

    input_price, output_price, cached_read_price = prices
    cache_creation_price = input_price * _CACHE_CREATION_MULTIPLIER

    million = Decimal("1000000")
    cost = (
        (input_tokens - cached_input_tokens - cache_creation_input_tokens) * input_price / million
        + output_tokens * output_price / million
        + cached_input_tokens * cached_read_price / million
        + cache_creation_input_tokens * cache_creation_price / million
    )
    return max(cost, Decimal("0")).quantize(Decimal("0.000001"))
