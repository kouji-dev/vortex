"""Tool provider flat-rate pricing table for the chat domain.

Prices are per-call USD amounts. A rate of 0 means the provider is free to use.
"""
from __future__ import annotations

from decimal import Decimal


_FLAT_RATES: dict[str, Decimal] = {
    "duckduckgo": Decimal("0"),
    "serper": Decimal("0.0003"),
    "tavily": Decimal("0.008"),
    "firecrawl": Decimal("0.002"),
    "jina": Decimal("0.001"),
    "crawl4ai": Decimal("0"),
    "kb_search": Decimal("0"),
}


def get_tool_flat_rate(provider: str) -> Decimal | None:
    return _FLAT_RATES.get(provider)
