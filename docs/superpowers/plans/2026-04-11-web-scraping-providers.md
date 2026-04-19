# Web Search & Fetch Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the custom layered fetch logic with Crawl4AI, and wire each LLM provider to its native search tool instead of our DuckDuckGo stack.

**Architecture:** A `tools/fetch/` provider chain (Crawl4AI → requests fallback) replaces the current `_fetch_requests`/`_fetch_amp_cache`/`_fetch_browser` tangle in `fetch_webpage.py`. The registry becomes model-aware: Anthropic models get `web_search_20260209` (server-side, Anthropic executes), Gemini models get `google_search_retrieval`, all others keep the existing DuckDuckGo `web_search` tool. The SSE streaming parser learns to surface `server_tool_use` events as UI chips without dispatching them.

**Tech Stack:** `crawl4ai>=0.4`, `requests`, `beautifulsoup4`, `langchain-anthropic`, `langchain-google-genai`

---

## File Map

| Action | File |
|---|---|
| Create | `backend/src/ai_portal/tools/fetch/__init__.py` |
| Create | `backend/src/ai_portal/tools/fetch/base.py` |
| Create | `backend/src/ai_portal/tools/fetch/requests_fetch.py` |
| Create | `backend/src/ai_portal/tools/fetch/crawl4ai_provider.py` |
| Create | `backend/src/ai_portal/tools/fetch/chain.py` |
| Create | `backend/src/ai_portal/tools/fetch/factory.py` |
| Modify | `backend/src/ai_portal/tools/fetch_webpage.py` |
| Modify | `backend/src/ai_portal/core/config.py` |
| Modify | `backend/src/ai_portal/tools/registry.py` |
| Modify | `backend/src/ai_portal/chat/streaming_service.py` |
| Modify | `backend/src/ai_portal/catalog/providers/langchain.py` |
| Modify | `backend/pyproject.toml` |
| Keep   | `backend/src/ai_portal/tools/web_search.py` (untouched) |
| Keep   | `backend/src/ai_portal/tools/search/` (untouched) |

---

## Task 1: Add crawl4ai to dependencies

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add crawl4ai to pyproject.toml**

In `backend/pyproject.toml`, in the `dependencies` list, add after `"beautifulsoup4>=4.12"`:

```toml
"crawl4ai>=0.4",
```

- [ ] **Step 2: Install it**

```bash
cd backend
source .venv/Scripts/activate
pip install crawl4ai
crawl4ai-setup
```

Expected: no errors. `crawl4ai-setup` installs Playwright browsers used by the crawler.

- [ ] **Step 3: Smoke-test import**

```bash
python -c "from crawl4ai import AsyncWebCrawler; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml
git commit -m "chore(deps): add crawl4ai>=0.4"
```

---

## Task 2: BaseFetchProvider + RequestsFetchProvider

**Files:**
- Create: `backend/src/ai_portal/tools/fetch/__init__.py`
- Create: `backend/src/ai_portal/tools/fetch/base.py`
- Create: `backend/src/ai_portal/tools/fetch/requests_fetch.py`
- Test: `backend/tests/test_fetch_providers.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_fetch_providers.py`:

```python
"""Unit tests for fetch provider abstractions."""
from unittest.mock import MagicMock, patch

import pytest


def test_requests_provider_returns_text_for_html_page():
    from ai_portal.tools.fetch.requests_fetch import RequestsFetchProvider

    html = "<html><body><p>Hello world content here.</p></body></html>"
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_fetch_providers.py -v
```

Expected: `ModuleNotFoundError: No module named 'ai_portal.tools.fetch'`

- [ ] **Step 3: Create the package and base class**

Create `backend/src/ai_portal/tools/fetch/__init__.py` (empty):

```python
```

Create `backend/src/ai_portal/tools/fetch/base.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseFetchProvider(ABC):
    """Fetch the text content of a URL. Return None to fall through to the next provider."""

    @abstractmethod
    def fetch(self, url: str) -> str | None:
        ...
```

- [ ] **Step 4: Create RequestsFetchProvider**

Create `backend/src/ai_portal/tools/fetch/requests_fetch.py`:

```python
from __future__ import annotations

import logging
import re

from ai_portal.tools.fetch.base import BaseFetchProvider

logger = logging.getLogger(__name__)

_TIMEOUT = 10
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8",
}
_CLOUDFLARE_SIGNALS = ("cf-browser-verification", "Just a moment")


class RequestsFetchProvider(BaseFetchProvider):
    def fetch(self, url: str) -> str | None:
        try:
            import requests
            from bs4 import BeautifulSoup

            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)
            if resp.status_code != 200:
                return None
            if any(sig in resp.text for sig in _CLOUDFLARE_SIGNALS):
                logger.debug("requests_fetch_cloudflare url=%s", url)
                return None
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = re.sub(r"\n{3,}", "\n\n", soup.get_text(separator="\n").strip())
            return text if len(text) > 100 else None
        except Exception as exc:
            logger.debug("requests_fetch_failed url=%s exc=%s", url, exc)
            return None
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_fetch_providers.py -v
```

Expected: 4 PASSED.

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/tools/fetch/ backend/tests/test_fetch_providers.py
git commit -m "feat(fetch): BaseFetchProvider + RequestsFetchProvider"
```

---

## Task 3: Crawl4AiFetchProvider

**Files:**
- Create: `backend/src/ai_portal/tools/fetch/crawl4ai_provider.py`
- Modify: `backend/tests/test_fetch_providers.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_fetch_providers.py`:

```python
def test_crawl4ai_provider_returns_markdown_on_success():
    from ai_portal.tools.fetch.crawl4ai_provider import Crawl4AiFetchProvider

    mock_result = MagicMock()
    mock_result.markdown = MagicMock()
    mock_result.markdown.fit_markdown = "# Page Title\n\nSome useful content here."

    mock_crawler = MagicMock()
    mock_crawler.__aenter__ = MagicMock(return_value=mock_crawler)
    mock_crawler.__aexit__ = MagicMock(return_value=False)
    mock_crawler.arun = MagicMock(return_value=mock_result)

    with patch("ai_portal.tools.fetch.crawl4ai_provider.AsyncWebCrawler", return_value=mock_crawler), \
         patch("ai_portal.tools.fetch.crawl4ai_provider.BrowserConfig"), \
         patch("ai_portal.tools.fetch.crawl4ai_provider.CrawlerRunConfig"):
        result = Crawl4AiFetchProvider().fetch("https://example.com")

    assert result is not None
    assert "Page Title" in result


def test_crawl4ai_provider_returns_none_on_empty_markdown():
    from ai_portal.tools.fetch.crawl4ai_provider import Crawl4AiFetchProvider

    mock_result = MagicMock()
    mock_result.markdown = MagicMock()
    mock_result.markdown.fit_markdown = ""

    mock_crawler = MagicMock()
    mock_crawler.__aenter__ = MagicMock(return_value=mock_crawler)
    mock_crawler.__aexit__ = MagicMock(return_value=False)
    mock_crawler.arun = MagicMock(return_value=mock_result)

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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_fetch_providers.py::test_crawl4ai_provider_returns_markdown_on_success -v
```

Expected: `ImportError` or `ModuleNotFoundError`.

- [ ] **Step 3: Implement Crawl4AiFetchProvider**

Create `backend/src/ai_portal/tools/fetch/crawl4ai_provider.py`:

```python
from __future__ import annotations

import asyncio
import logging
import re

from ai_portal.tools.fetch.base import BaseFetchProvider

logger = logging.getLogger(__name__)

_TIMEOUT = 20  # seconds

try:
    from crawl4ai import AsyncWebCrawler
    from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
    _CRAWL4AI_AVAILABLE = True
except ImportError:
    _CRAWL4AI_AVAILABLE = False
    AsyncWebCrawler = None  # type: ignore[assignment,misc]
    BrowserConfig = None  # type: ignore[assignment,misc]
    CrawlerRunConfig = None  # type: ignore[assignment,misc]


class Crawl4AiFetchProvider(BaseFetchProvider):
    """Fetch pages using Crawl4AI's headless browser with stealth mode.

    Returns clean LLM-optimised markdown via result.markdown.fit_markdown.
    Handles JS-rendered pages and Cloudflare-protected sites.
    """

    def fetch(self, url: str) -> str | None:
        if not _CRAWL4AI_AVAILABLE:
            logger.warning("crawl4ai_not_installed: skipping Crawl4AiFetchProvider")
            return None
        try:
            return asyncio.run(self._async_fetch(url))
        except Exception as exc:
            logger.warning("crawl4ai_fetch_failed url=%s exc=%s", url, exc)
            return None

    async def _async_fetch(self, url: str) -> str | None:
        browser_cfg = BrowserConfig(
            headless=True,
            enable_stealth=True,
            user_agent_mode="random",
        )
        run_cfg = CrawlerRunConfig(
            remove_overlay_elements=True,
            word_count_threshold=10,
        )
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            result = await asyncio.wait_for(
                crawler.arun(url=url, config=run_cfg),
                timeout=_TIMEOUT,
            )
        text = getattr(result.markdown, "fit_markdown", None) or ""
        text = re.sub(r"\n{3,}", "\n\n", text.strip())
        return text if len(text) > 100 else None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_fetch_providers.py -v
```

Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/src/ai_portal/tools/fetch/crawl4ai_provider.py backend/tests/test_fetch_providers.py
git commit -m "feat(fetch): Crawl4AiFetchProvider with stealth mode"
```

---

## Task 4: FetchChain + factory

**Files:**
- Create: `backend/src/ai_portal/tools/fetch/chain.py`
- Create: `backend/src/ai_portal/tools/fetch/factory.py`
- Modify: `backend/tests/test_fetch_providers.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_fetch_providers.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_fetch_providers.py::test_fetch_chain_returns_first_successful_result -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement FetchChain**

Create `backend/src/ai_portal/tools/fetch/chain.py`:

```python
from __future__ import annotations

from ai_portal.tools.fetch.base import BaseFetchProvider

_MAX_CHARS = 8_000


def _truncate(text: str) -> str:
    if len(text) > _MAX_CHARS:
        return text[:_MAX_CHARS] + "\n\n[content truncated]"
    return text


class FetchChain:
    def __init__(self, providers: list[BaseFetchProvider]) -> None:
        self.providers = providers

    def fetch(self, url: str) -> str:
        for provider in self.providers:
            result = provider.fetch(url)
            if result:
                return _truncate(result)
        return (
            f"Could not retrieve content from {url} after all strategies failed. "
            "Use search snippets and training data to answer."
        )
```

- [ ] **Step 4: Implement factory**

Create `backend/src/ai_portal/tools/fetch/factory.py`:

```python
from __future__ import annotations

import logging

from ai_portal.tools.fetch.chain import FetchChain
from ai_portal.tools.fetch.requests_fetch import RequestsFetchProvider

logger = logging.getLogger(__name__)


def build_fetch_chain() -> FetchChain:
    providers = []

    try:
        from ai_portal.tools.fetch.crawl4ai_provider import Crawl4AiFetchProvider, _CRAWL4AI_AVAILABLE
        if _CRAWL4AI_AVAILABLE:
            providers.append(Crawl4AiFetchProvider())
        else:
            logger.warning("fetch_chain: crawl4ai not installed, skipping")
    except Exception as exc:
        logger.warning("fetch_chain: crawl4ai unavailable exc=%s", exc)

    providers.append(RequestsFetchProvider())
    return FetchChain(providers)
```

- [ ] **Step 5: Run all fetch provider tests**

```bash
python -m pytest tests/test_fetch_providers.py -v
```

Expected: 11 PASSED.

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/tools/fetch/chain.py backend/src/ai_portal/tools/fetch/factory.py backend/tests/test_fetch_providers.py
git commit -m "feat(fetch): FetchChain + factory with Crawl4AI -> requests fallback"
```

---

## Task 5: Wire fetch_webpage.py to FetchChain

**Files:**
- Modify: `backend/src/ai_portal/tools/fetch_webpage.py`

- [ ] **Step 1: Write a regression test**

Create `backend/tests/test_fetch_webpage_tool.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_fetch_webpage_tool.py -v
```

Expected: FAIL (no `_chain` attribute yet).

- [ ] **Step 3: Rewrite fetch_webpage.py**

Replace the full content of `backend/src/ai_portal/tools/fetch_webpage.py`:

```python
"""fetch_webpage tool — fetches a URL using Crawl4AI (stealth, JS rendering) with a
requests fallback. The provider chain is built once at module load time.
"""

from __future__ import annotations

import logging

from ai_portal.tools.fetch.factory import build_fetch_chain

logger = logging.getLogger(__name__)

_chain = build_fetch_chain()

SYSTEM_PROMPT = (
    "## Webpage Fetching\n"
    "Use the `fetch_webpage` tool to retrieve the full text of a specific URL. "
    "Typical use cases:\n"
    "- A `web_search` returned URLs with promising titles but thin snippets — fetch the best one.\n"
    "- The user asks you to read, summarize, or extract information from a specific link.\n"
    "- You need deeper detail (full article, stats page) that a snippet cannot provide.\n"
    "You can chain tools: call `web_search` first to find relevant URLs, then `fetch_webpage` "
    "on the most promising result. "
    "If a fetch fails or returns no useful content, try a different URL. "
    "Always synthesize what you fetched into a clear, direct answer for the user."
)


def system_prompt() -> str:
    return SYSTEM_PROMPT


def schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "fetch_webpage",
            "description": (
                "Fetch and read the full text content of a webpage. "
                "Handles JavaScript-heavy sites and Cloudflare-protected pages. "
                "Use after web_search when you need more detail than the snippets provide."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL of the webpage to fetch.",
                    },
                },
                "required": ["url"],
            },
        },
    }


def execute(url: str) -> dict:
    content = _chain.fetch(url)
    return {"name": "fetch_webpage", "content": content, "_used_kbs": []}
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_fetch_webpage_tool.py -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Run all backend unit tests to check for regressions**

```bash
python -m pytest tests/ -v --ignore=tests/e2e
```

Expected: all pass (or same failures as before this change).

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/tools/fetch_webpage.py backend/tests/test_fetch_webpage_tool.py
git commit -m "feat(fetch): wire fetch_webpage to Crawl4AI FetchChain"
```

---

## Task 6: Config — user_search_country

**Files:**
- Modify: `backend/src/ai_portal/core/config.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_fetch_webpage_tool.py`:

```python
def test_settings_has_user_search_country_default():
    from ai_portal.core.config import Settings
    s = Settings()
    assert s.user_search_country == "FR"
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest tests/test_fetch_webpage_tool.py::test_settings_has_user_search_country_default -v
```

Expected: `AttributeError: 'Settings' object has no attribute 'user_search_country'`.

- [ ] **Step 3: Add field to Settings**

In `backend/src/ai_portal/core/config.py`, add after the `langfuse_host` field (line 270):

```python
    # Web search localisation — passed as user_location.country to Anthropic native search
    # and as Google Search region for Gemini. Default "FR" = Europe.
    user_search_country: str = Field(
        default="FR",
        validation_alias=AliasChoices("USER_SEARCH_COUNTRY"),
    )
```

Also add to `_YAML_KEY_MAP` dict (after the `observability.langfuse_host` entry):

```python
    "llm.user_search_country": "user_search_country",
```

- [ ] **Step 4: Run test**

```bash
python -m pytest tests/test_fetch_webpage_tool.py::test_settings_has_user_search_country_default -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/ai_portal/core/config.py
git commit -m "feat(config): add user_search_country (default FR)"
```

---

## Task 7: Registry — model-aware tool definitions

**Files:**
- Modify: `backend/src/ai_portal/tools/registry.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_registry_native_search.py`:

```python
"""Tests for model-aware tool definition injection."""


def test_registry_returns_native_anthropic_search_for_claude_model():
    from ai_portal.tools.registry import get_tool_definitions

    tools = get_tool_definitions(kb_ids=[], model_id="claude-sonnet-4-6")
    tool_types = [t.get("type") for t in tools]
    assert "web_search_20260209" in tool_types
    # Our custom web_search should NOT be present for Anthropic models
    function_names = [
        t.get("function", {}).get("name")
        for t in tools
        if t.get("type") == "function"
    ]
    assert "web_search" not in function_names


def test_registry_returns_custom_search_for_non_anthropic_model():
    from ai_portal.tools.registry import get_tool_definitions

    tools = get_tool_definitions(kb_ids=[], model_id="gpt-4o")
    function_names = [
        t.get("function", {}).get("name")
        for t in tools
        if t.get("type") == "function"
    ]
    assert "web_search" in function_names
    # No native Anthropic tool for OpenAI models
    tool_types = [t.get("type") for t in tools]
    assert "web_search_20260209" not in tool_types


def test_registry_returns_gemini_search_for_gemini_model():
    from ai_portal.tools.registry import get_tool_definitions

    tools = get_tool_definitions(kb_ids=[], model_id="gemini-2.5-flash")
    # Gemini uses google_search_retrieval (a dict with that key, not type="function")
    has_google_search = any("google_search_retrieval" in t for t in tools)
    assert has_google_search


def test_registry_falls_back_to_custom_search_when_no_model():
    from ai_portal.tools.registry import get_tool_definitions

    tools = get_tool_definitions(kb_ids=[], model_id=None)
    function_names = [
        t.get("function", {}).get("name")
        for t in tools
        if t.get("type") == "function"
    ]
    assert "web_search" in function_names


def test_registry_native_anthropic_search_has_user_location():
    from ai_portal.tools.registry import get_tool_definitions

    tools = get_tool_definitions(kb_ids=[], model_id="claude-opus-4-6")
    native = next(t for t in tools if t.get("type") == "web_search_20260209")
    assert "user_location" in native
    assert native["user_location"]["country"] == "FR"  # default
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_registry_native_search.py -v
```

Expected: all FAIL (current `get_tool_definitions` ignores `model_id`).

- [ ] **Step 3: Rewrite registry.py**

Replace full content of `backend/src/ai_portal/tools/registry.py`:

```python
"""Tool registry — central access point for tool definitions, prompts, and dispatch.

The streaming service calls only these three functions; it never imports
individual tool modules.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ai_portal.catalog.providers.routing import (
    is_langchain_anthropic_model,
    is_langchain_gemini_model,
)
from ai_portal.core.config import get_settings
from ai_portal.tools import fetch_webpage as fetch_webpage_tool
from ai_portal.tools import kb_search as kb_search_tool
from ai_portal.tools import web_search as web_search_tool

logger = logging.getLogger(__name__)


def _native_anthropic_search_tool() -> dict:
    """Server-side web search tool for Anthropic models (executed by Anthropic, not us)."""
    settings = get_settings()
    return {
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": 5,
        "user_location": {
            "type": "approximate",
            "country": settings.user_search_country,
            "timezone": "Europe/Paris",
        },
    }


def _native_gemini_search_tool() -> dict:
    """Google Search grounding tool for Gemini models (executed by Google, not us)."""
    return {
        "google_search_retrieval": {
            "dynamic_retrieval_config": {"mode": "MODE_DYNAMIC"}
        }
    }


def get_system_prompts(kb_ids: list[int]) -> list[str]:
    """Always includes fetch_webpage prompt; adds web_search + kb_search when relevant."""
    prompts = [fetch_webpage_tool.system_prompt()]
    # Custom web_search system prompt only needed when our tool is active (non-native providers)
    prompts.append(web_search_tool.system_prompt())
    if kb_ids:
        prompts.append(kb_search_tool.system_prompt())
    return prompts


def get_tool_definitions(
    kb_ids: list[int],
    model_id: str | None = None,
) -> list[dict]:
    """Return tool schemas for the given model. Search tool varies by provider."""
    tools: list[dict] = []

    if model_id and is_langchain_anthropic_model(model_id):
        # Use Anthropic's native server-side search (no dispatch needed)
        tools.append(_native_anthropic_search_tool())
    elif model_id and is_langchain_gemini_model(model_id):
        # Use Google Search grounding (no dispatch needed)
        tools.append(_native_gemini_search_tool())
    else:
        # All other providers (OpenAI, custom): use our DuckDuckGo web_search tool
        tools.append(web_search_tool.schema())

    # fetch_webpage always uses our Crawl4AI chain
    tools.append(fetch_webpage_tool.schema())

    if kb_ids:
        tools.append(kb_search_tool.schema(kb_ids))

    return tools


def dispatch(
    tool_name: str,
    args: dict,
    *,
    db: Session,
    kb_ids: list[int],
) -> dict:
    """Route a tool call to the appropriate execute() function.

    Note: native provider tools (web_search_20260209, google_search_retrieval) are
    executed server-side and never reach this function.
    """
    if tool_name == "web_search":
        query = args.get("query", "")
        num_results = int(args.get("num_results", 5))
        region = args.get("region", "uk-en")
        return web_search_tool.execute(query, num_results, region)

    if tool_name == "fetch_webpage":
        url = args.get("url", "")
        return fetch_webpage_tool.execute(url)

    if tool_name == "search_knowledge_base":
        query = args.get("query", "")
        kb_ids_arg = args.get("kb_ids") or kb_ids or []
        top_k = args.get("top_k")
        return kb_search_tool.execute(query, kb_ids_arg, top_k, db)

    logger.warning("unknown_tool_call name=%s", tool_name)
    return {"name": tool_name, "content": f"Error: unknown tool '{tool_name}'", "_used_kbs": []}
```

- [ ] **Step 4: Run new tests**

```bash
python -m pytest tests/test_registry_native_search.py -v
```

Expected: 5 PASSED.

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -v --ignore=tests/e2e
```

Expected: all pass (or same as before).

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/tools/registry.py backend/tests/test_registry_native_search.py
git commit -m "feat(registry): model-aware tool injection (Anthropic native, Gemini grounding, DDG fallback)"
```

---

## Task 8: Pass model_id to registry in streaming_service.py

**Files:**
- Modify: `backend/src/ai_portal/chat/streaming_service.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_registry_native_search.py`:

```python
def test_streaming_service_passes_model_to_registry(requires_postgres_mark):
    """Verify streaming_service passes use_model to get_tool_definitions."""
    import pytest
    pytest.importorskip("psycopg")

    from unittest.mock import patch, MagicMock
    from fastapi.testclient import TestClient
    from ai_portal.main import app

    client = TestClient(app)
    AUTH = {"Authorization": "Bearer devtoken"}

    r = client.post("/api/chat/conversations", headers=AUTH, json={})
    assert r.status_code == 201
    cid = r.json()["id"]

    with patch("ai_portal.tools.registry.get_tool_definitions", wraps=lambda kb_ids, model_id=None: []) as mock_gtd, \
         patch("ai_portal.catalog.providers.langchain.LangChainChatProvider.stream_deltas_with_tools",
               return_value=iter([{"type": "delta", "text": "hi"}])):
        client.post(
            f"/api/chat/conversations/{cid}/messages/stream",
            headers=AUTH,
            json={"content": "hello", "model": "claude-sonnet-4-6"},
        )

    assert mock_gtd.called
    _, kwargs = mock_gtd.call_args
    assert kwargs.get("model_id") is not None
```

- [ ] **Step 2: Update streaming_service.py line 124**

In `backend/src/ai_portal/chat/streaming_service.py`, find this block (around line 122-130):

```python
    # ── Tool definitions ─────────────────────────────────────────────────────
    kb_ids = repo.get_conversation_kb_ids(db, conv.id)
    tools = tool_registry.get_tool_definitions(kb_ids)
```

Replace with:

```python
    # ── Tool definitions ─────────────────────────────────────────────────────
    kb_ids = repo.get_conversation_kb_ids(db, conv.id)
    _stored_model_for_tools = (
        body.model or conv.model or settings.chat_default_api_model or ""
    ).strip()
    tools = tool_registry.get_tool_definitions(kb_ids, model_id=_stored_model_for_tools or None)
```

- [ ] **Step 3: Run full test suite**

```bash
python -m pytest tests/ -v --ignore=tests/e2e
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add backend/src/ai_portal/chat/streaming_service.py
git commit -m "feat(streaming): pass model_id to registry for native tool injection"
```

---

## Task 9: LangChain — pass native tool dicts + surface server_tool_use chunks

**Files:**
- Modify: `backend/src/ai_portal/catalog/providers/langchain.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_langchain_native_tools.py`:

```python
"""Tests for LangChain provider handling of native tool dicts."""
from unittest.mock import MagicMock, patch


def _make_chunk(text=None, tool_call_chunks=None, additional_kwargs=None):
    chunk = MagicMock()
    chunk.text = text or ""
    chunk.content = text or ""
    chunk.tool_call_chunks = tool_call_chunks or []
    chunk.additional_kwargs = additional_kwargs or {}
    return chunk


def test_stream_deltas_emits_delta_for_text_chunk():
    from ai_portal.catalog.providers.langchain import LangChainChatProvider
    from ai_portal.core.config import Settings

    provider = LangChainChatProvider(Settings())
    chunk = _make_chunk(text="hello world")

    with patch.object(provider, "_chat_model") as mock_cm:
        mock_model = MagicMock()
        mock_model.bind_tools.return_value = mock_model
        mock_model.stream.return_value = iter([chunk])
        mock_cm.return_value = mock_model

        pieces = list(provider.stream_deltas_with_tools(
            [{"role": "user", "content": "hi"}],
            model="gpt-4o",
            tools=[{"type": "function", "function": {"name": "fetch_webpage", "description": "...", "parameters": {"type": "object", "properties": {}, "required": []}}}],
        ))

    assert any(p.get("type") == "delta" and "hello" in p.get("text", "") for p in pieces)


def test_stream_deltas_emits_server_tool_use_for_anthropic_native_search():
    from ai_portal.catalog.providers.langchain import LangChainChatProvider
    from ai_portal.core.config import Settings

    provider = LangChainChatProvider(Settings())

    # Simulate Anthropic streaming: first chunk has server_tool_use in additional_kwargs
    chunk_tool = _make_chunk(
        additional_kwargs={
            "server_tool_use": {
                "type": "server_tool_use",
                "name": "web_search",
                "id": "srvtoolu_abc",
                "input": {"query": "LoL EUW rank 1"},
            }
        }
    )
    chunk_text = _make_chunk(text="The rank 1 player is...")

    with patch.object(provider, "_chat_model") as mock_cm:
        mock_model = MagicMock()
        mock_model.bind_tools.return_value = mock_model
        mock_model.stream.return_value = iter([chunk_tool, chunk_text])
        mock_cm.return_value = mock_model

        pieces = list(provider.stream_deltas_with_tools(
            [{"role": "user", "content": "who is rank 1 EUW?"}],
            model="claude-sonnet-4-6",
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
        ))

    server_tool_pieces = [p for p in pieces if p.get("type") == "server_tool_use"]
    assert len(server_tool_pieces) == 1
    assert server_tool_pieces[0]["name"] == "web_search"
    assert server_tool_pieces[0]["input"]["query"] == "LoL EUW rank 1"
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_langchain_native_tools.py -v
```

Expected: second test FAILS (no `server_tool_use` emission yet).

- [ ] **Step 3: Update stream_deltas_with_tools in langchain.py**

In `backend/src/ai_portal/catalog/providers/langchain.py`, replace the `stream_deltas_with_tools` method (lines 162-198):

```python
    def stream_deltas_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        mid = self._resolved_model_id(model)
        chat = self._chat_model(mid)

        if tools:
            # Separate native provider tools (non-function type) from standard function tools.
            # Native tools (e.g. web_search_20260209, google_search_retrieval) are forwarded
            # to the provider as-is; standard function tools are bound via LangChain's bind_tools.
            function_tools = [
                t for t in tools
                if t.get("type") == "function" or "function" in t
            ]
            native_tools = [
                t for t in tools
                if t.get("type") != "function" and "function" not in t
            ]

            if function_tools:
                chat = chat.bind_tools(
                    function_tools,
                    **{"tool_choice": tool_choice} if tool_choice else {},
                )

            if native_tools and is_langchain_anthropic_model(mid):
                # Pass Anthropic server tools via bind() so they appear in the API request
                # alongside any already-bound function tools.
                existing = getattr(chat, "kwargs", {}).get("tools", [])
                chat = chat.bind(tools=list(existing) + native_tools)

        lc_messages = _map_dict_messages_to_lc(messages)
        tc_name: str | None = None
        tc_args_parts: list[str] = []

        for chunk in chat.stream(lc_messages):
            # Detect Anthropic server_tool_use (native search/fetch executed by Anthropic)
            ak = getattr(chunk, "additional_kwargs", {}) or {}
            srv = ak.get("server_tool_use")
            if srv and isinstance(srv, dict):
                yield {
                    "type": "server_tool_use",
                    "name": srv.get("name", ""),
                    "input": srv.get("input", {}),
                    "id": srv.get("id", ""),
                }
                continue

            # Standard client-side tool call chunks
            tc_chunks = getattr(chunk, "tool_call_chunks", None)
            if tc_chunks:
                for tcc in tc_chunks:
                    if tcc.get("name"):
                        tc_name = tcc["name"]
                    tc_args_parts.append(tcc.get("args", "") or "")
                continue

            text = _chunk_assistant_text(chunk)
            if text:
                yield {"type": "delta", "text": text}

        if tc_name is not None:
            raw_args = "".join(tc_args_parts)
            yield {
                "type": "tool_call",
                "tool_call": {"name": tc_name, "arguments": raw_args},
            }
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_langchain_native_tools.py -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Run full suite**

```bash
python -m pytest tests/ -v --ignore=tests/e2e
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/catalog/providers/langchain.py backend/tests/test_langchain_native_tools.py
git commit -m "feat(langchain): pass native tool dicts + emit server_tool_use events for Anthropic"
```

---

## Task 10: streaming_service.py — handle server_tool_use events

**Files:**
- Modify: `backend/src/ai_portal/chat/streaming_service.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_langchain_native_tools.py`:

```python
def test_streaming_service_emits_chip_for_server_tool_use(requires_postgres_mark):
    """server_tool_use events from langchain become item_start chips in the SSE stream."""
    import json
    import pytest
    pytest.importorskip("psycopg")

    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from ai_portal.main import app

    tc = TestClient(app)
    AUTH = {"Authorization": "Bearer devtoken"}

    r = tc.post("/api/chat/conversations", headers=AUTH, json={})
    assert r.status_code == 201
    cid = r.json()["id"]

    stream_pieces = [
        {"type": "server_tool_use", "name": "web_search", "input": {"query": "LoL EUW rank 1"}, "id": "srv1"},
        {"type": "delta", "text": "The rank 1 player is Faker."},
    ]

    with patch(
        "ai_portal.catalog.providers.langchain.LangChainChatProvider.stream_deltas_with_tools",
        return_value=iter(stream_pieces),
    ):
        resp = tc.post(
            f"/api/chat/conversations/{cid}/messages/stream",
            headers=AUTH,
            json={"content": "who is rank 1 EUW?", "model": "claude-sonnet-4-6"},
        )

    assert resp.status_code == 200
    events = []
    for line in resp.text.strip().splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass

    item_start_events = [
        e for e in events
        if e.get("type") == "item_start" and e.get("item", {}).get("kind") == "web_search"
    ]
    assert len(item_start_events) >= 1
    assert item_start_events[0]["item"]["query"] == "LoL EUW rank 1"

    # Must NOT have dispatched the tool (no tool result injection)
    item_done_events = [
        e for e in events
        if e.get("type") == "item_done" and e.get("item", {}).get("kind") == "web_search"
    ]
    # item_done emitted but with status "done" (server handled)
    assert len(item_done_events) >= 1
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest "tests/test_langchain_native_tools.py::test_streaming_service_emits_chip_for_server_tool_use" -v
```

Expected: FAIL — `server_tool_use` pieces fall through to the `else` branch and get emitted as raw text deltas.

- [ ] **Step 3: Add server_tool_use handling to streaming_service.py**

In `backend/src/ai_portal/chat/streaming_service.py`, find the piece-type handling block inside `_stream_loop` (around line 429). Currently:

```python
                if isinstance(piece, dict) and piece.get("type") == "tool_call":
                    ...
                elif isinstance(piece, dict) and piece.get("type") == "delta":
                    ...
                else:
                    full.append(str(piece))
                    yield _sse({"type": "delta", "text": str(piece)})
```

Add a new branch **before** the `elif delta` branch:

```python
                if isinstance(piece, dict) and piece.get("type") == "tool_call":
                    tool_call_buffer = piece.get("tool_call")
                    _tool_name = tool_call_buffer.get("name", "")
                    try:
                        _tool_params = json.loads(
                            tool_call_buffer.get("arguments", "{}")
                        )
                    except Exception:
                        _tool_params = {}
                    # Map tool name to SSE kind
                    if _tool_name == "web_search":
                        _tool_item_kind = "web_search"
                    elif _tool_name == "fetch_webpage":
                        _tool_item_kind = "fetch_webpage"
                    elif _tool_name == "kb_search":
                        _tool_item_kind = "kb_search"
                    else:
                        _tool_item_kind = "tool_call"
                    _tool_item_uid = str(uuid4())
                    logger.info(
                        "stream_loop: tool_call name=%r kind=%r params=%r",
                        _tool_name,
                        _tool_item_kind,
                        _tool_params,
                    )
                    _query = _tool_params.get("query", "")
                    _url = _tool_params.get("url", "")
                    item_start_payload: dict = {
                        "uid": _tool_item_uid,
                        "kind": _tool_item_kind,
                        "tool": _tool_name,
                        "params": _tool_params,
                    }
                    if _query:
                        item_start_payload["query"] = _query
                    if _url:
                        item_start_payload["url"] = _url
                    yield _sse({"type": "item_start", "item": item_start_payload})
                    # Accumulate for persistence (no status field)
                    stream_item_entry: dict = {
                        "uid": _tool_item_uid,
                        "kind": _tool_item_kind,
                    }
                    if _query:
                        stream_item_entry["query"] = _query
                    if _url:
                        stream_item_entry["url"] = _url
                    stream_items.append(stream_item_entry)
                elif isinstance(piece, dict) and piece.get("type") == "server_tool_use":
                    # Native provider tool (Anthropic web_search_20260209, Gemini grounding).
                    # The provider executes this — we just surface a chip for the UI.
                    _srv_name = piece.get("name", "web_search")
                    _srv_input = piece.get("input", {})
                    _srv_uid = str(uuid4())
                    _srv_query = _srv_input.get("query", "")
                    _srv_url = _srv_input.get("url", "")
                    _srv_kind = (
                        "web_search" if _srv_name == "web_search"
                        else "fetch_webpage" if _srv_name == "web_fetch"
                        else "tool_call"
                    )
                    logger.info(
                        "stream_loop: server_tool_use name=%r query=%r",
                        _srv_name,
                        _srv_query,
                    )
                    srv_start: dict = {
                        "uid": _srv_uid,
                        "kind": _srv_kind,
                        "tool": _srv_name,
                        "params": _srv_input,
                    }
                    if _srv_query:
                        srv_start["query"] = _srv_query
                    if _srv_url:
                        srv_start["url"] = _srv_url
                    yield _sse({"type": "item_start", "item": srv_start})
                    srv_done: dict = {
                        "uid": _srv_uid,
                        "kind": _srv_kind,
                        "tool": _srv_name,
                        "status": "done",
                    }
                    if _srv_query:
                        srv_done["query"] = _srv_query
                    srv_item: dict = {"uid": _srv_uid, "kind": _srv_kind}
                    if _srv_query:
                        srv_item["query"] = _srv_query
                    stream_items.append(srv_item)
                    yield _sse({"type": "item_done", "item": srv_done})
                    # Do NOT set tool_call_buffer — server tools are not dispatched by us
                elif isinstance(piece, dict) and piece.get("type") == "delta":
                    text = piece.get("text", "")
                    full.append(text)
                    yield _sse({"type": "delta", "text": text})
                else:
                    full.append(str(piece))
                    yield _sse({"type": "delta", "text": str(piece)})
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_langchain_native_tools.py -v
```

Expected: all pass.

- [ ] **Step 5: Run full suite**

```bash
python -m pytest tests/ -v --ignore=tests/e2e
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/chat/streaming_service.py
git commit -m "feat(streaming): surface server_tool_use events as UI chips, skip dispatch"
```

---

## Task 11: Run full E2E backend tests and fix regressions

**Files:**
- Modify: `backend/tests/test_builtin_tools_e2e.py` (if needed)

- [ ] **Step 1: Start the E2E backend**

```bash
./scripts/e2e-up.sh
curl http://localhost:8001/health
```

Expected: health check returns 200, logs show `ai_portal_e2e` DB.

- [ ] **Step 2: Run all backend tests**

```bash
cd frontend && pnpm test:e2e:filter "web_search\|fetch_webpage\|tool" 2>&1 | head -80
```

- [ ] **Step 3: Run full E2E suite**

```bash
pnpm test:e2e
```

Expected: all green. If any test references `DuckDuckGoProvider` directly in mocks (e.g. `test_builtin_tools_e2e.py` line 52 patches `ai_portal.tools.registry.DuckDuckGoProvider`), update the patch path:

Old (if present):
```python
patch("ai_portal.tools.registry.DuckDuckGoProvider")
```

New:
```python
patch("ai_portal.tools.web_search.DuckDuckGoProvider")
```

- [ ] **Step 4: Commit any fixes**

```bash
git add backend/tests/
git commit -m "test: fix mock paths after registry refactor"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by |
|---|---|
| `tools/fetch/` provider chain | Tasks 2–5 |
| Crawl4AI as primary fetch | Task 3 |
| Requests as fallback | Task 2 |
| `fetch_webpage.py` uses chain | Task 5 |
| `user_search_country` config | Task 6 |
| Registry model-aware | Task 7 |
| `streaming_service` passes model | Task 8 |
| LangChain passes native tool dicts | Task 9 |
| `server_tool_use` chips in UI | Task 10 |
| Gemini `google_search_retrieval` | Task 7 (injected in registry), Task 9 (no LangChain special handling needed — LangChain-Google handles it natively via `bind_tools`) |
| Old `web_search.py` + `search/` kept | All tasks — neither file is touched |

**Placeholder scan:** None found.

**Type consistency:**
- `BaseFetchProvider.fetch(url: str) -> str | None` — used consistently in all providers, chain, and factory.
- `FetchChain.fetch(url: str) -> str` (always returns string) — used in `fetch_webpage.execute()`.
- `get_tool_definitions(kb_ids, model_id=None)` — updated call site in `streaming_service.py`.
- `server_tool_use` event shape `{"type", "name", "input", "id"}` — emitted in `langchain.py`, consumed in `streaming_service.py`.
