"""Jina Reader fetch provider.

Prepends r.jina.ai/ to any URL and returns clean markdown.
Handles JS-rendered pages via Puppeteer. Does not bypass Cloudflare,
but is a reliable zero-cost fallback for open pages.

Free tier: 20 RPM without key, 500 RPM with free API key (no CC required).
Sign up: https://jina.ai (get a free API key for higher rate limit)
"""

from __future__ import annotations

import logging

import requests

from ai_portal.tools.fetch.base import BaseFetchProvider

logger = logging.getLogger(__name__)

_BASE_URL = "https://r.jina.ai/"
_TIMEOUT = 30


class JinaFetchProvider(BaseFetchProvider):
    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key

    def fetch(self, url: str) -> str | None:
        try:
            headers: dict[str, str] = {
                "Accept": "text/plain",
                "X-Return-Format": "markdown",
            }
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            resp = requests.get(
                f"{_BASE_URL}{url}",
                headers=headers,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            text = resp.text.strip()
            return text if len(text) > 100 else None
        except Exception as exc:
            logger.debug("jina_fetch_failed url=%s exc=%s", url, exc)
            return None
