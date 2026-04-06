from unittest.mock import MagicMock, patch

from ai_portal.tools.search.base import BaseSearchProvider, SearchResult


def test_search_result_fields():
    r = SearchResult(title="T", url="https://example.com", snippet="S")
    assert r.title == "T"
    assert r.url == "https://example.com"
    assert r.snippet == "S"


def test_base_provider_is_abstract():
    import pytest
    with pytest.raises(TypeError):
        BaseSearchProvider()  # cannot instantiate abstract class


def test_duckduckgo_provider_returns_search_results():
    mock_results = [
        {"title": "Result 1", "href": "https://a.com", "body": "Snippet 1"},
        {"title": "Result 2", "href": "https://b.com", "body": "Snippet 2"},
    ]
    with patch("ai_portal.tools.search.duckduckgo.DDGS") as MockDDGS:
        instance = MagicMock()
        instance.text.return_value = mock_results
        MockDDGS.return_value.__enter__ = MagicMock(return_value=instance)
        MockDDGS.return_value.__exit__ = MagicMock(return_value=False)

        from ai_portal.tools.search.duckduckgo import DuckDuckGoProvider
        provider = DuckDuckGoProvider()
        results = provider.search("python web frameworks", num_results=2)

    assert len(results) == 2
    assert results[0].title == "Result 1"
    assert results[0].url == "https://a.com"
    assert results[0].snippet == "Snippet 1"
    assert results[1].title == "Result 2"


def test_duckduckgo_provider_handles_empty_results():
    with patch("ai_portal.tools.search.duckduckgo.DDGS") as MockDDGS:
        instance = MagicMock()
        instance.text.return_value = []
        MockDDGS.return_value.__enter__ = MagicMock(return_value=instance)
        MockDDGS.return_value.__exit__ = MagicMock(return_value=False)

        from ai_portal.tools.search.duckduckgo import DuckDuckGoProvider
        provider = DuckDuckGoProvider()
        results = provider.search("xkcd", num_results=5)

    assert results == []


def test_duckduckgo_provider_handles_exception():
    with patch("ai_portal.tools.search.duckduckgo.DDGS") as MockDDGS:
        instance = MagicMock()
        instance.text.side_effect = Exception("rate limited")
        MockDDGS.return_value.__enter__ = MagicMock(return_value=instance)
        MockDDGS.return_value.__exit__ = MagicMock(return_value=False)

        from ai_portal.tools.search.duckduckgo import DuckDuckGoProvider
        provider = DuckDuckGoProvider()
        results = provider.search("test")

    assert results == []
