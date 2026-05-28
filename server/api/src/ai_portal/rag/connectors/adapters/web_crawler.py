"""Web Crawler connector — sitemap + URL seed.

Discovery rules:
- if a seed URL ends in ``.xml`` (or is otherwise treated as a sitemap),
  parse it as a ``urlset`` and yield each ``<loc>`` entry.
- otherwise, yield the seed URL itself.

Three governance behaviours are mandatory:

1. **robots.txt** — fetched once per host, cached. If ``respect_robots`` is
   ``True`` (default) and the URL is disallowed, it is skipped silently.
2. **Delta cursor** — a single ISO-8601 ``lastmod`` watermark. On ``discover``
   any sitemap entry with ``<lastmod>`` ≤ cursor is suppressed. Entries
   without ``lastmod`` always pass through.
3. **Per-host rate limit** — fetch concurrency is gated by a per-host
   semaphore sized to ``rate_per_domain_rps``.

Fetched bytes are returned verbatim — extraction happens downstream in the
pipeline.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, AsyncIterator
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree as ET

import httpx

from ai_portal.rag.connectors import register
from ai_portal.rag.connectors.manifest import ConnectorManifest
from ai_portal.rag.connectors.protocol import (
    AclSet,
    FetchedDoc,
    SourceDoc,
)

_MANIFEST = ConnectorManifest(
    name="web_crawler",
    auth_kinds=("none",),
    schedulable=True,
    supports_delta=True,
    supports_acl=False,
    supports_webhook=False,
    config_schema={
        "type": "object",
        "required": ["seed_urls"],
        "properties": {
            "seed_urls": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 0,
            },
            "max_depth": {"type": "integer", "default": 3, "minimum": 1},
            "rate_per_domain_rps": {
                "type": "number",
                "default": 1.0,
                "exclusiveMinimum": 0,
            },
            "respect_robots": {"type": "boolean", "default": True},
        },
    },
)

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _parse_iso(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


class WebCrawlerConnector:
    """Public web crawler. Public-ACL only; no auth required."""

    manifest = _MANIFEST

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._cursor: str | None = None
        self._robots_cache: dict[str, RobotFileParser | None] = {}
        self._sem_per_host: dict[str, asyncio.Semaphore] = {}

    # ----------------------------------------------------------- lifecycle --

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "WebCrawlerConnector":
        return cls(config)

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor

    # ----------------------------------------------------------- discover --

    async def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        cursor_dt = _parse_iso(cursor) if cursor else None
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=15.0
        ) as client:
            for seed in self._config.get("seed_urls", []):
                async for sd in self._walk_seed(client, seed, cursor_dt):
                    yield sd

    async def _walk_seed(
        self,
        client: httpx.AsyncClient,
        seed: str,
        cursor_dt: datetime | None,
    ) -> AsyncIterator[SourceDoc]:
        host = urlparse(seed).netloc
        rp = (
            await self._robots_for(client, host)
            if self._config.get("respect_robots", True)
            else None
        )
        if self._looks_like_sitemap(client, seed):
            async for sd in self._iter_sitemap(client, seed, rp, cursor_dt):
                yield sd
            return
        if rp is not None and not rp.can_fetch("*", seed):
            return
        yield SourceDoc(
            source_uri=seed,
            title=seed,
            mime="text/html",
            size=None,
            modified_at=None,
            cursor_token=None,
            raw={},
        )

    @staticmethod
    def _looks_like_sitemap(
        client: httpx.AsyncClient, url: str
    ) -> bool:  # noqa: ARG004 - signature parity for future detection
        return url.endswith(".xml") or url.endswith("/sitemap.xml")

    async def _iter_sitemap(
        self,
        client: httpx.AsyncClient,
        url: str,
        rp: RobotFileParser | None,
        cursor_dt: datetime | None,
    ) -> AsyncIterator[SourceDoc]:
        res = await client.get(url)
        if res.status_code >= 400:
            return
        try:
            root = ET.fromstring(res.content)
        except ET.ParseError:
            return
        for u in root.findall("sm:url", _SITEMAP_NS):
            loc = u.findtext("sm:loc", namespaces=_SITEMAP_NS)
            if not loc:
                continue
            lastmod_raw = u.findtext("sm:lastmod", namespaces=_SITEMAP_NS)
            lastmod = _parse_iso(lastmod_raw) if lastmod_raw else None
            if rp is not None and not rp.can_fetch("*", loc):
                continue
            if cursor_dt and lastmod and lastmod <= cursor_dt:
                continue
            yield SourceDoc(
                source_uri=loc,
                title=loc,
                mime="text/html",
                size=None,
                modified_at=lastmod,
                cursor_token=lastmod.isoformat() if lastmod else None,
                raw={},
            )

    # ----------------------------------------------------------- robots --

    async def _robots_for(
        self, client: httpx.AsyncClient, host: str
    ) -> RobotFileParser | None:
        if host in self._robots_cache:
            return self._robots_cache[host]
        rp = RobotFileParser()
        try:
            res = await client.get(f"https://{host}/robots.txt")
            if res.status_code == 200:
                rp.parse(res.text.splitlines())
            else:
                # Missing robots ⇒ no restrictions (RFC 9309 implicit allow)
                rp = None  # type: ignore[assignment]
        except Exception:
            rp = None  # type: ignore[assignment]
        self._robots_cache[host] = rp
        return rp

    # ----------------------------------------------------------- fetch --

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        rps = float(self._config.get("rate_per_domain_rps", 1.0))
        host = urlparse(sd.source_uri).netloc
        sem = self._sem_per_host.setdefault(
            host, asyncio.Semaphore(max(1, int(rps)))
        )
        async with sem:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=30.0
            ) as client:
                r = await client.get(sd.source_uri)
                r.raise_for_status()
                ctype = (
                    r.headers.get("content-type", "text/html")
                    .split(";", 1)[0]
                    .strip()
                )
                return FetchedDoc(
                    data=r.content,
                    mime=ctype,
                    meta={
                        "status": r.status_code,
                        "etag": r.headers.get("etag"),
                        "last_modified": r.headers.get("last-modified"),
                    },
                )

    async def acls(self, sd: SourceDoc) -> AclSet:
        return AclSet(public=True)


register(WebCrawlerConnector)
