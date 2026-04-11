from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from ai_portal.tools.fetch.base import BaseFetchProvider

logger = logging.getLogger(__name__)

_TIMEOUT = 10
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8",
}
_CLOUDFLARE_SIGNALS = ("cf-browser-verification", "Just a moment")


class RequestsFetchProvider(BaseFetchProvider):
    def fetch(self, url: str) -> str | None:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)
            if resp.status_code != 200:
                return None
            if any(sig in resp.text for sig in _CLOUDFLARE_SIGNALS):
                logger.debug("requests_fetch_cloudflare url=%s", url)
                return None
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = re.sub(r"\n{3,}", "\n\n", soup.get_text(separator="\n").strip())
            return text if len(text) > 100 else None
        except Exception as exc:
            logger.debug("requests_fetch_failed url=%s exc=%s", url, exc)
            return None
