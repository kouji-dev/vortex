from decimal import Decimal
from ai_portal.chat.tool_pricing import get_tool_flat_rate


def test_known_providers():
    assert get_tool_flat_rate("duckduckgo") == Decimal("0")
    assert get_tool_flat_rate("tavily") == Decimal("0.008")
    assert get_tool_flat_rate("firecrawl") == Decimal("0.002")


def test_unknown_provider_returns_none():
    assert get_tool_flat_rate("nonsense") is None
