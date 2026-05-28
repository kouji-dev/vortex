"""HTTP-backed providers (tavily, exa, brave, bing, google_cse) — using
a stubbed `httpx.Client` so no network is required.

Each test asserts that:
  - The provider returns SearchProviderResult dataclasses in API order.
  - Empty API key short-circuits to [].
  - Network/parse errors degrade to [].
"""
from __future__ import annotations

from typing import Any

import httpx
import pytest

from ai_portal.rag.search_providers.protocol import SearchProviderResult
from ai_portal.rag.search_providers.providers.bing import BingProvider
from ai_portal.rag.search_providers.providers.brave import BraveProvider
from ai_portal.rag.search_providers.providers.exa import ExaProvider
from ai_portal.rag.search_providers.providers.google_cse import GoogleCseProvider
from ai_portal.rag.search_providers.providers.tavily import TavilyProvider


class _StubClient:
    """httpx-shaped stub. ``responses`` is an iterable of (status, json)."""

    def __init__(self, payload: Any, status: int = 200):
        self._payload = payload
        self._status = status

    def _make_resp(self):
        req = httpx.Request("GET", "https://stub")
        return httpx.Response(self._status, json=self._payload, request=req)

    def post(self, *args, **kwargs):
        return self._make_resp()

    def get(self, *args, **kwargs):
        return self._make_resp()


# ---------------------------------------------------------------------------
# Tavily
# ---------------------------------------------------------------------------


def test_tavily_returns_ordered_results():
    payload = {
        "results": [
            {"title": "A", "url": "https://a", "content": "snip A", "score": 0.9},
            {"title": "B", "url": "https://b", "content": "snip B", "score": 0.6},
        ]
    }
    p = TavilyProvider(api_key="k", client=_StubClient(payload))
    out = p.search("q", num_results=2)
    assert [r.title for r in out] == ["A", "B"]
    assert isinstance(out[0], SearchProviderResult)
    assert out[0].source == "tavily"
    assert out[0].score == 0.9


def test_tavily_empty_key_returns_empty():
    p = TavilyProvider(api_key="")
    assert p.search("q") == []


def test_tavily_http_error_returns_empty():
    p = TavilyProvider(api_key="k", client=_StubClient({}, status=500))
    assert p.search("q") == []


# ---------------------------------------------------------------------------
# Exa
# ---------------------------------------------------------------------------


def test_exa_returns_results():
    payload = {
        "results": [
            {"title": "X", "url": "https://x", "text": "tx", "score": 0.7},
        ]
    }
    p = ExaProvider(api_key="k", client=_StubClient(payload))
    out = p.search("q")
    assert out[0].title == "X"
    assert out[0].source == "exa"


def test_exa_no_key_returns_empty():
    assert ExaProvider().search("q") == []


# ---------------------------------------------------------------------------
# Brave
# ---------------------------------------------------------------------------


def test_brave_returns_results():
    payload = {
        "web": {
            "results": [
                {"title": "BB", "url": "https://bb", "description": "desc"}
            ]
        }
    }
    p = BraveProvider(api_key="k", client=_StubClient(payload))
    out = p.search("q")
    assert out[0].title == "BB"
    assert out[0].source == "brave"


# ---------------------------------------------------------------------------
# Bing
# ---------------------------------------------------------------------------


def test_bing_returns_results():
    payload = {
        "webPages": {
            "value": [
                {"name": "Page1", "url": "https://p1", "snippet": "sn"}
            ]
        }
    }
    p = BingProvider(api_key="k", client=_StubClient(payload))
    out = p.search("q")
    assert out[0].title == "Page1"
    assert out[0].snippet == "sn"
    assert out[0].source == "bing"


# ---------------------------------------------------------------------------
# Google CSE
# ---------------------------------------------------------------------------


def test_google_cse_returns_results():
    payload = {
        "items": [
            {"title": "G", "link": "https://g", "snippet": "sn"}
        ]
    }
    p = GoogleCseProvider(api_key="k", cx="cx", client=_StubClient(payload))
    out = p.search("q")
    assert out[0].title == "G"
    assert out[0].url == "https://g"


def test_google_cse_missing_cx_returns_empty():
    assert GoogleCseProvider(api_key="k", cx="").search("q") == []


# ---------------------------------------------------------------------------
# Ordering preservation across providers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_cls,payload,key", [
    (
        TavilyProvider,
        {"results": [{"title": str(i), "url": f"u{i}", "content": "c"} for i in range(3)]},
        "k",
    ),
    (
        ExaProvider,
        {"results": [{"title": str(i), "url": f"u{i}", "text": "c"} for i in range(3)]},
        "k",
    ),
    (
        BraveProvider,
        {"web": {"results": [{"title": str(i), "url": f"u{i}", "description": "d"} for i in range(3)]}},
        "k",
    ),
])
def test_provider_preserves_api_order(provider_cls, payload, key):
    p = provider_cls(api_key=key, client=_StubClient(payload))
    out = p.search("q", num_results=3)
    assert [r.title for r in out] == ["0", "1", "2"]
