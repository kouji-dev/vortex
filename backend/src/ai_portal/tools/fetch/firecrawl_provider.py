"""Firecrawl fetch provider.

Hosted API with Fire-engine: handles Cloudflare JS challenges, JS-rendered pages,
residential IP rotation. Best free-tier option for bot-protected pages.

Free tier: 500 credits/month, no credit card required.
Sign up: https://firecrawl.dev
"""

from __future__ import annotations

import logging

import requests

from ai_portal.tools.fetch.base import BaseFetchProvider

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.firecrawl.dev/v1/scrape"
_TIMEOUT = 30


class FirecrawlFetchProvider(BaseFetchProvider):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def fetch(self, url: str) -> str | None:
        try:
            resp = requests.post(
                _ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"url": url, "formats": ["markdown"]},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            text = (data.get("data") or {}).get("markdown") or ""
            return text if len(text) > 100 else None
        except Exception as exc:
            logger.debug("firecrawl_fetch_failed url=%s exc=%s", url, exc)
            return None
