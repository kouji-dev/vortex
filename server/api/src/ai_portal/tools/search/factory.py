"""Search provider factory.

Reads ``search_provider`` from settings and returns the appropriate provider.
Falls back to DuckDuckGo if the configured provider has no API key set.
"""

from __future__ import annotations

import logging

from ai_portal.tools.search.base import BaseSearchProvider

logger = logging.getLogger(__name__)


def build_search_provider() -> BaseSearchProvider:
    from ai_portal.core.config import get_settings
    from ai_portal.tools.search.duckduckgo import DuckDuckGoProvider

    settings = get_settings()
    provider_name = (settings.search_provider or "duckduckgo").strip().lower()

    if provider_name == "tavily":
        if settings.tavily_api_key:
            from ai_portal.tools.search.tavily import TavilyProvider
            logger.debug("search_factory: using TavilyProvider")
            return TavilyProvider(api_key=settings.tavily_api_key)
        logger.warning("search_factory: tavily selected but TAVILY_API_KEY not set — falling back to DuckDuckGo")

    elif provider_name == "serper":
        if settings.serper_api_key:
            from ai_portal.tools.search.serper import SerperProvider
            logger.debug("search_factory: using SerperProvider")
            return SerperProvider(api_key=settings.serper_api_key)
        logger.warning("search_factory: serper selected but SERPER_API_KEY not set — falling back to DuckDuckGo")

    elif provider_name == "exa":
        if settings.exa_api_key:
            from ai_portal.tools.search.exa import ExaProvider
            logger.debug("search_factory: using ExaProvider")
            return ExaProvider(api_key=settings.exa_api_key)
        logger.warning("search_factory: exa selected but EXA_API_KEY not set — falling back to DuckDuckGo")

    elif provider_name != "duckduckgo":
        logger.warning("search_factory: unknown provider %r — falling back to DuckDuckGo", provider_name)

    logger.debug("search_factory: using DuckDuckGoProvider")
    return DuckDuckGoProvider()
