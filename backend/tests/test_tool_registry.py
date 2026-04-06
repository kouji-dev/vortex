from unittest.mock import MagicMock, patch


def test_registry_dispatches_web_search():
    from ai_portal.tools.registry import ToolRegistry

    mock_results = []
    with patch("ai_portal.tools.registry.DuckDuckGoProvider") as MockProvider:
        instance = MagicMock()
        instance.search.return_value = mock_results
        MockProvider.return_value = instance

        registry = ToolRegistry()
        result = registry.dispatch("web_search", {"query": "test", "num_results": 3})

    instance.search.assert_called_once_with("test", num_results=3)
    assert result["role"] == "tool"
    assert result["name"] == "web_search"


def test_registry_formats_search_results():
    from ai_portal.tools.registry import ToolRegistry
    from ai_portal.tools.search.base import SearchResult

    mock_results = [
        SearchResult(title="Title A", url="https://a.com", snippet="Snippet A"),
        SearchResult(title="Title B", url="https://b.com", snippet="Snippet B"),
    ]
    with patch("ai_portal.tools.registry.DuckDuckGoProvider") as MockProvider:
        instance = MagicMock()
        instance.search.return_value = mock_results
        MockProvider.return_value = instance

        registry = ToolRegistry()
        result = registry.dispatch("web_search", {"query": "test"})

    content = result["content"]
    assert "Title A" in content
    assert "https://a.com" in content
    assert "Snippet A" in content
    assert "Title B" in content


def test_registry_web_search_no_results():
    from ai_portal.tools.registry import ToolRegistry

    with patch("ai_portal.tools.registry.DuckDuckGoProvider") as MockProvider:
        instance = MagicMock()
        instance.search.return_value = []
        MockProvider.return_value = instance

        registry = ToolRegistry()
        result = registry.dispatch("web_search", {"query": "obscure topic"})

    assert "no results" in result["content"].lower()


def test_registry_dispatches_query_structured_data():
    from ai_portal.tools.registry import ToolRegistry

    with patch("ai_portal.tools.registry.query_structured_data") as mock_qsd:
        mock_qsd.return_value = "The answer is 42."
        registry = ToolRegistry()
        result = registry.dispatch(
            "query_structured_data",
            {"data": "x,y\n1,2", "question": "what is x?"},
        )

    mock_qsd.assert_called_once_with("x,y\n1,2", "what is x?")
    assert result["content"] == "The answer is 42."
    assert result["role"] == "tool"
    assert result["name"] == "query_structured_data"


def test_registry_unknown_tool():
    from ai_portal.tools.registry import ToolRegistry

    registry = ToolRegistry()
    result = registry.dispatch("nonexistent_tool", {})

    assert result["role"] == "tool"
    assert "unknown tool" in result["content"].lower()
