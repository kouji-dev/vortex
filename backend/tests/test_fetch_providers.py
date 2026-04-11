"""Unit tests for fetch provider abstractions."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_requests_provider_returns_text_for_html_page():
    from ai_portal.tools.fetch.requests_fetch import RequestsFetchProvider

    html = "<html><body><p>Hello world content here. " + "This is a long paragraph. " * 10 + "</p></body></html>"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html

    with patch("ai_portal.tools.fetch.requests_fetch.requests") as mock_requests:
        mock_requests.get.return_value = mock_resp
        result = RequestsFetchProvider().fetch("https://example.com")

    assert result is not None
    assert "Hello world content here" in result


def test_requests_provider_returns_none_on_cloudflare():
    from ai_portal.tools.fetch.requests_fetch import RequestsFetchProvider

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "Just a moment... cf-browser-verification"

    with patch("ai_portal.tools.fetch.requests_fetch.requests") as mock_requests:
        mock_requests.get.return_value = mock_resp
        result = RequestsFetchProvider().fetch("https://protected.com")

    assert result is None


def test_requests_provider_returns_none_on_non_200():
    from ai_portal.tools.fetch.requests_fetch import RequestsFetchProvider

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"

    with patch("ai_portal.tools.fetch.requests_fetch.requests") as mock_requests:
        mock_requests.get.return_value = mock_resp
        result = RequestsFetchProvider().fetch("https://example.com")

    assert result is None


def test_requests_provider_returns_none_on_exception():
    from ai_portal.tools.fetch.requests_fetch import RequestsFetchProvider

    with patch("ai_portal.tools.fetch.requests_fetch.requests") as mock_requests:
        mock_requests.get.side_effect = Exception("connection error")
        result = RequestsFetchProvider().fetch("https://example.com")

    assert result is None


def _make_crawl4ai_mock(fit_markdown: str):
    """Build an async-compatible AsyncWebCrawler mock."""
    mock_result = MagicMock()
    mock_result.markdown = MagicMock()
    mock_result.markdown.fit_markdown = fit_markdown

    mock_crawler = AsyncMock()
    mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
    mock_crawler.__aexit__ = AsyncMock(return_value=False)
    mock_crawler.arun = AsyncMock(return_value=mock_result)
    return mock_crawler


def test_crawl4ai_provider_returns_markdown_on_success():
    from ai_portal.tools.fetch.crawl4ai_provider import Crawl4AiFetchProvider

    mock_crawler = _make_crawl4ai_mock("# Page Title\n\nSome useful content here. " + "x" * 200)

    with patch("ai_portal.tools.fetch.crawl4ai_provider.AsyncWebCrawler", return_value=mock_crawler), \
         patch("ai_portal.tools.fetch.crawl4ai_provider.BrowserConfig"), \
         patch("ai_portal.tools.fetch.crawl4ai_provider.CrawlerRunConfig"):
        result = Crawl4AiFetchProvider().fetch("https://example.com")

    assert result is not None
    assert "Page Title" in result


def test_crawl4ai_provider_returns_none_on_empty_markdown():
    from ai_portal.tools.fetch.crawl4ai_provider import Crawl4AiFetchProvider

    mock_crawler = _make_crawl4ai_mock("")

    with patch("ai_portal.tools.fetch.crawl4ai_provider.AsyncWebCrawler", return_value=mock_crawler), \
         patch("ai_portal.tools.fetch.crawl4ai_provider.BrowserConfig"), \
         patch("ai_portal.tools.fetch.crawl4ai_provider.CrawlerRunConfig"):
        result = Crawl4AiFetchProvider().fetch("https://example.com")

    assert result is None


def test_crawl4ai_provider_returns_none_on_exception():
    from ai_portal.tools.fetch.crawl4ai_provider import Crawl4AiFetchProvider

    with patch("ai_portal.tools.fetch.crawl4ai_provider.AsyncWebCrawler", side_effect=Exception("browser error")):
        result = Crawl4AiFetchProvider().fetch("https://example.com")

    assert result is None


def test_fetch_chain_returns_first_successful_result():
    from ai_portal.tools.fetch.base import BaseFetchProvider
    from ai_portal.tools.fetch.chain import FetchChain

    class AlwaysNone(BaseFetchProvider):
        def fetch(self, url):
            return None

    class ReturnsHello(BaseFetchProvider):
        def fetch(self, url):
            return "hello content"

    chain = FetchChain([AlwaysNone(), ReturnsHello()])
    result = chain.fetch("https://example.com")
    assert result == "hello content"


def test_fetch_chain_returns_failure_message_when_all_fail():
    from ai_portal.tools.fetch.base import BaseFetchProvider
    from ai_portal.tools.fetch.chain import FetchChain

    class AlwaysNone(BaseFetchProvider):
        def fetch(self, url):
            return None

    chain = FetchChain([AlwaysNone(), AlwaysNone()])
    result = chain.fetch("https://example.com")
    assert "Could not retrieve" in result
    assert "https://example.com" in result


def test_fetch_chain_truncates_long_content():
    from ai_portal.tools.fetch.base import BaseFetchProvider
    from ai_portal.tools.fetch.chain import FetchChain, _MAX_CHARS

    class LongContent(BaseFetchProvider):
        def fetch(self, url):
            return "x" * (_MAX_CHARS + 1000)

    chain = FetchChain([LongContent()])
    result = chain.fetch("https://example.com")
    assert len(result) <= _MAX_CHARS + 50  # allow for truncation marker
    assert "truncated" in result


def test_fetch_factory_builds_chain():
    from ai_portal.tools.fetch.factory import build_fetch_chain
    from ai_portal.tools.fetch.chain import FetchChain

    chain = build_fetch_chain()
    assert isinstance(chain, FetchChain)
    assert len(chain.providers) >= 1
