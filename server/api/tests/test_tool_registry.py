"""Tests for the tool registry dispatch() function."""
from unittest.mock import MagicMock, patch


def test_registry_dispatches_web_search():
    from ai_portal.tools import registry
    from ai_portal.tools.search.base import SearchResult

    mock_results = [SearchResult(title="T", url="https://a.com", snippet="S")]
    db = MagicMock()
    with patch("ai_portal.tools.web_search.build_search_provider") as mock_factory:
        instance = MagicMock()
        instance.search.return_value = mock_results
        instance.name = "duckduckgo"
        mock_factory.return_value = instance

        result = registry.dispatch("web_search", {"query": "test", "num_results": 3}, db=db, kb_ids=[])

    assert result["name"] == "web_search"
    assert "T" in result["content"]


def test_registry_formats_search_results():
    from ai_portal.tools import registry
    from ai_portal.tools.search.base import SearchResult

    mock_results = [
        SearchResult(title="Title A", url="https://a.com", snippet="Snippet A"),
        SearchResult(title="Title B", url="https://b.com", snippet="Snippet B"),
    ]
    db = MagicMock()
    with patch("ai_portal.tools.web_search.build_search_provider") as mock_factory:
        instance = MagicMock()
        instance.search.return_value = mock_results
        instance.name = "duckduckgo"
        mock_factory.return_value = instance

        result = registry.dispatch("web_search", {"query": "test"}, db=db, kb_ids=[])

    content = result["content"]
    assert "Title A" in content
    assert "https://a.com" in content
    assert "Snippet A" in content
    assert "Title B" in content


def test_registry_web_search_no_results():
    from ai_portal.tools import registry

    db = MagicMock()
    with patch("ai_portal.tools.web_search.build_search_provider") as mock_factory:
        instance = MagicMock()
        instance.search.return_value = []
        instance.name = "duckduckgo"
        mock_factory.return_value = instance

        result = registry.dispatch("web_search", {"query": "obscure topic"}, db=db, kb_ids=[])

    assert "no results" in result["content"].lower()


def test_registry_unknown_tool():
    from ai_portal.tools import registry

    db = MagicMock()
    result = registry.dispatch("nonexistent_tool", {}, db=db, kb_ids=[])

    assert "unknown tool" in result["content"].lower()
