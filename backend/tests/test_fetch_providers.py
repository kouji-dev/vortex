"""Unit tests for fetch provider abstractions."""
from unittest.mock import MagicMock, patch

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
