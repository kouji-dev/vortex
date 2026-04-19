from __future__ import annotations

import asyncio
import logging
import os
import re

from ai_portal.tools.fetch.base import BaseFetchProvider

# Ensure subprocess stdout can handle Unicode on Windows (Crawl4AI uses Playwright).
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

logger = logging.getLogger(__name__)

_TIMEOUT = 20  # seconds

try:
    from crawl4ai import AsyncWebCrawler
    from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
    _CRAWL4AI_AVAILABLE = True
except ImportError:
    _CRAWL4AI_AVAILABLE = False
    AsyncWebCrawler = None  # type: ignore[assignment,misc]
    BrowserConfig = None  # type: ignore[assignment,misc]
    CrawlerRunConfig = None  # type: ignore[assignment,misc]


class Crawl4AiFetchProvider(BaseFetchProvider):
    """Fetch pages using Crawl4AI's headless browser with stealth mode.

    Returns clean LLM-optimised markdown via result.markdown.fit_markdown.
    Handles JS-rendered pages and Cloudflare-protected sites.
    """

    def fetch(self, url: str) -> str | None:
        if not _CRAWL4AI_AVAILABLE:
            logger.warning("crawl4ai_not_installed: skipping Crawl4AiFetchProvider")
            return None
        try:
            return asyncio.run(self._async_fetch(url))
        except Exception as exc:
            logger.warning("crawl4ai_fetch_failed url=%s exc=%s", url, exc)
            return None

    async def _async_fetch(self, url: str) -> str | None:
        browser_cfg = BrowserConfig(
            headless=True,
            enable_stealth=True,
            user_agent_mode="random",
        )
        run_cfg = CrawlerRunConfig(
            remove_overlay_elements=True,
            word_count_threshold=10,
        )
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            result = await asyncio.wait_for(
                crawler.arun(url=url, config=run_cfg),
                timeout=_TIMEOUT,
            )
        text = getattr(result.markdown, "fit_markdown", None) or ""
        text = re.sub(r"\n{3,}", "\n\n", text.strip())
        return text if len(text) > 100 else None
