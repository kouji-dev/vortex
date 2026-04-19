"""Fetch chain factory.

Chain order (first success wins):
  1. Firecrawl  — best bot/Cloudflare bypass (hosted API, requires key)
  2. Crawl4AI   — Playwright + stealth, handles JS (local, no key needed)
  3. Jina Reader — clean markdown via r.jina.ai, handles JS (free, no key needed)
  4. requests   — plain HTTP fallback
"""

from __future__ import annotations

import logging

from ai_portal.tools.fetch.chain import FetchChain
from ai_portal.tools.fetch.requests_fetch import RequestsFetchProvider

logger = logging.getLogger(__name__)


def build_fetch_chain() -> FetchChain:
    from ai_portal.core.config import get_settings

    settings = get_settings()
    providers = []

    # 1. Firecrawl — best Cloudflare bypass, requires API key
    if settings.firecrawl_api_key:
        try:
            from ai_portal.tools.fetch.firecrawl_provider import FirecrawlFetchProvider

            providers.append(FirecrawlFetchProvider(api_key=settings.firecrawl_api_key))
            logger.debug("fetch_chain: FirecrawlFetchProvider added")
        except Exception as exc:
            logger.warning("fetch_chain: firecrawl unavailable exc=%s", exc)
    else:
        logger.debug("fetch_chain: firecrawl skipped (no FIRECRAWL_API_KEY)")

    # 2. Crawl4AI — local Playwright + stealth, no key needed
    try:
        from ai_portal.tools.fetch.crawl4ai_provider import (
            _CRAWL4AI_AVAILABLE,
            Crawl4AiFetchProvider,
        )

        if _CRAWL4AI_AVAILABLE:
            providers.append(Crawl4AiFetchProvider())
            logger.debug("fetch_chain: Crawl4AiFetchProvider added")
        else:
            logger.debug("fetch_chain: crawl4ai not installed, skipping")
    except Exception as exc:
        logger.warning("fetch_chain: crawl4ai unavailable exc=%s", exc)

    # 3. Jina Reader — clean markdown via r.jina.ai, always available
    try:
        from ai_portal.tools.fetch.jina_provider import JinaFetchProvider

        providers.append(JinaFetchProvider(api_key=settings.jina_api_key or ""))
        logger.debug(
            "fetch_chain: JinaFetchProvider added (key=%s)", bool(settings.jina_api_key)
        )
    except Exception as exc:
        logger.warning("fetch_chain: jina unavailable exc=%s", exc)

    # 4. requests — plain HTTP last resort, always present
    providers.append(RequestsFetchProvider())

    logger.debug(
        "fetch_chain: built with %d providers: %s",
        len(providers),
        [type(p).__name__ for p in providers],
    )
    return FetchChain(providers)
