from __future__ import annotations

import logging

from ai_portal.tools.fetch.chain import FetchChain
from ai_portal.tools.fetch.requests_fetch import RequestsFetchProvider

logger = logging.getLogger(__name__)


def build_fetch_chain() -> FetchChain:
    providers = []

    try:
        from ai_portal.tools.fetch.crawl4ai_provider import Crawl4AiFetchProvider, _CRAWL4AI_AVAILABLE
        if _CRAWL4AI_AVAILABLE:
            providers.append(Crawl4AiFetchProvider())
        else:
            logger.warning("fetch_chain: crawl4ai not installed, skipping")
    except Exception as exc:
        logger.warning("fetch_chain: crawl4ai unavailable exc=%s", exc)

    providers.append(RequestsFetchProvider())
    return FetchChain(providers)
