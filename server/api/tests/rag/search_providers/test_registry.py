"""Registry resolves bundled providers; rejects unknowns."""
from __future__ import annotations

import pytest

from ai_portal.rag.search_providers import get_provider, list_providers
from ai_portal.rag.search_providers.registry import UnknownSearchProvider


def test_bundled_providers_registered():
    names = list_providers()
    for expected in ("tavily", "exa", "brave", "bing", "google_cse", "internal_kbs"):
        assert expected in names


def test_get_provider_returns_named():
    p = get_provider("tavily", api_key="dummy")
    assert p.name == "tavily"


def test_get_provider_unknown_raises():
    with pytest.raises(UnknownSearchProvider):
        get_provider("nope")
