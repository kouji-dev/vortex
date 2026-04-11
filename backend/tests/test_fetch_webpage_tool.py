"""Regression test — fetch_webpage.execute() must use FetchChain."""
from unittest.mock import patch


def test_fetch_webpage_execute_uses_chain():
    from ai_portal.tools import fetch_webpage

    with patch("ai_portal.tools.fetch_webpage._chain") as mock_chain:
        mock_chain.fetch.return_value = "scraped content"
        result = fetch_webpage.execute("https://example.com")

    assert result["name"] == "fetch_webpage"
    assert result["content"] == "scraped content"
    mock_chain.fetch.assert_called_once_with("https://example.com")


def test_fetch_webpage_execute_returns_failure_message():
    from ai_portal.tools import fetch_webpage

    with patch("ai_portal.tools.fetch_webpage._chain") as mock_chain:
        mock_chain.fetch.return_value = "Could not retrieve content from https://example.com"
        result = fetch_webpage.execute("https://example.com")

    assert "Could not retrieve" in result["content"]
