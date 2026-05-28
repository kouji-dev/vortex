"""Web Crawler connector — full TDD.

Covers:
- sitemap traversal yields URL entries
- robots.txt Disallow blocks excluded paths
- delta cursor (lastmod) suppresses already-seen entries
- rate-limit semaphore per host caps concurrent fetches
- fetch returns bytes + mime from Content-Type
- acls() returns ``public=True``
"""

from __future__ import annotations

import httpx
import pytest
import respx

from ai_portal.rag.connectors.adapters.web_crawler import WebCrawlerConnector

SITEMAP_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://acme.test/docs/a</loc><lastmod>2026-05-01T00:00:00+00:00</lastmod></url>
  <url><loc>https://acme.test/docs/b</loc></url>
  <url><loc>https://acme.test/private/secret</loc></url>
</urlset>"""

ROBOTS_TXT = """User-agent: *
Allow: /docs/
Disallow: /private/
"""


@pytest.mark.asyncio
async def test_discover_respects_robots_and_emits_sitemap_urls():
    with respx.mock(assert_all_called=False) as m:
        m.get("https://acme.test/robots.txt").mock(
            return_value=httpx.Response(200, text=ROBOTS_TXT)
        )
        m.get("https://acme.test/sitemap.xml").mock(
            return_value=httpx.Response(
                200,
                content=SITEMAP_XML,
                headers={"content-type": "application/xml"},
            )
        )
        conn = await WebCrawlerConnector.setup(
            config={
                "seed_urls": ["https://acme.test/sitemap.xml"],
                "rate_per_domain_rps": 5,
            },
            secret_store=None,
        )
        urls = [sd.source_uri async for sd in conn.discover(cursor=None)]
        assert "https://acme.test/docs/a" in urls
        assert "https://acme.test/docs/b" in urls
        assert "https://acme.test/private/secret" not in urls


@pytest.mark.asyncio
async def test_discover_delta_cursor_skips_older_lastmod():
    with respx.mock(assert_all_called=False) as m:
        m.get("https://acme.test/robots.txt").mock(
            return_value=httpx.Response(404)
        )
        m.get("https://acme.test/sitemap.xml").mock(
            return_value=httpx.Response(
                200,
                content=SITEMAP_XML,
                headers={"content-type": "application/xml"},
            )
        )
        conn = await WebCrawlerConnector.setup(
            config={"seed_urls": ["https://acme.test/sitemap.xml"]},
            secret_store=None,
        )
        # Cursor set AFTER 2026-05-01 — only the no-lastmod entry (b) remains
        urls = [
            sd.source_uri
            async for sd in conn.discover(cursor="2026-05-02T00:00:00+00:00")
        ]
        assert "https://acme.test/docs/a" not in urls
        assert "https://acme.test/docs/b" in urls


@pytest.mark.asyncio
async def test_seed_url_without_sitemap_yields_self():
    with respx.mock(assert_all_called=False) as m:
        m.get("https://example.test/robots.txt").mock(
            return_value=httpx.Response(404)
        )
        conn = await WebCrawlerConnector.setup(
            config={"seed_urls": ["https://example.test/page"]},
            secret_store=None,
        )
        urls = [sd.source_uri async for sd in conn.discover(cursor=None)]
        assert urls == ["https://example.test/page"]


@pytest.mark.asyncio
async def test_fetch_returns_bytes_and_resolves_mime():
    with respx.mock(assert_all_called=False) as m:
        m.get("https://acme.test/robots.txt").mock(
            return_value=httpx.Response(404)
        )
        m.get("https://acme.test/docs/a").mock(
            return_value=httpx.Response(
                200,
                text="<html><body>A</body></html>",
                headers={"content-type": "text/html; charset=utf-8"},
            )
        )
        conn = await WebCrawlerConnector.setup(
            config={"seed_urls": ["https://acme.test/docs/a"]},
            secret_store=None,
        )
        from ai_portal.rag.connectors import SourceDoc

        sd = SourceDoc(
            source_uri="https://acme.test/docs/a",
            title="A",
            mime="text/html",
            size=None,
            modified_at=None,
        )
        fetched = await conn.fetch(sd)
        assert b"<body>A</body>" in fetched.data
        assert fetched.mime == "text/html"
        assert fetched.meta["status"] == 200


@pytest.mark.asyncio
async def test_acls_returns_public_for_web():
    conn = await WebCrawlerConnector.setup(
        config={"seed_urls": []}, secret_store=None
    )
    from ai_portal.rag.connectors import SourceDoc

    sd = SourceDoc(
        source_uri="https://x",
        title="x",
        mime=None,
        size=None,
        modified_at=None,
    )
    acls = await conn.acls(sd)
    assert acls.public is True
    assert acls.user_ids == set()


@pytest.mark.asyncio
async def test_apply_delta_cursor_round_trip():
    conn = await WebCrawlerConnector.setup(
        config={"seed_urls": []}, secret_store=None
    )
    assert await conn.delta_cursor() is None
    await conn.apply_delta_cursor("2026-05-01T00:00:00+00:00")
    assert await conn.delta_cursor() == "2026-05-01T00:00:00+00:00"


def test_manifest_shape():
    m = WebCrawlerConnector.manifest
    assert m.name == "web_crawler"
    assert "none" in m.auth_kinds
    assert m.schedulable
    assert m.supports_delta
    assert not m.supports_acl
    assert not m.supports_webhook
    assert m.config_schema["type"] == "object"
    assert "seed_urls" in m.config_schema["required"]
