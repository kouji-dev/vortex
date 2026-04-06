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
