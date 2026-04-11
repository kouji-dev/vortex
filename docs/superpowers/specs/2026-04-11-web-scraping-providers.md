# Web Search & Fetch Rework — Design Spec

**Date:** 2026-04-11

---

## Goal

Stop maintaining a custom web search stack. Delegate search entirely to each LLM provider's native tool. Own only the fetch/scrape layer, powered by Crawl4AI for JS rendering and Cloudflare bypass.

---

## Core Principle

| Concern | Owner | Rationale |
|---|---|---|
| Web search | LLM provider (native tool) | Anthropic, Gemini, OpenAI all have high-quality built-in search — no point duplicating |
| Webpage fetch / scrape | Our backend (Crawl4AI) | Native fetch tools don't handle JS-rendered pages; we need Crawl4AI for sites like op.gg |

---

## Part 1 — Native Search Per Provider

### Claude (Anthropic)

Add `web_search_20260209` as a server-side tool. Anthropic executes it — our backend dispatches nothing.

```python
{
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": 5,
    "user_location": {
        "type": "approximate",
        "country": "FR",        # European results by default
        "timezone": "Europe/Paris"
    }
}
```

- **Cost**: $10 / 1,000 searches + token costs
- **Quality**: Anthropic-managed, citations always included
- **Localization**: `user_location.country = "FR"` gives European results natively — solves the EUW issue

### Gemini (Google)

Enable Google Search grounding via `google_search_retrieval` tool. Google executes it.

```python
{"google_search_retrieval": {"dynamic_retrieval_config": {"mode": "MODE_DYNAMIC"}}}
```

- **Cost**: included in Gemini API pricing
- **Quality**: actual Google results

### OpenAI

Add the built-in web search tool via the Responses API. OpenAI executes it.

```python
{"type": "web_search_preview"}
```

- **Cost**: additional per-search fee on top of tokens

### Streaming — `server_tool_use` blocks (Claude)

Claude's native tools return `server_tool_use` content blocks in the SSE stream, not `tool_use`. Our streaming parser must:
1. Recognize `server_tool_use` blocks and surface them as tool chips in the UI (showing the query)
2. Recognize `web_search_tool_result` blocks and pass them back in conversation history
3. **Not** attempt to dispatch them — Anthropic handles execution

This is the main backend streaming change required.

---

## Part 2 — Fetch Provider Chain

We own this. The LLM calls our `fetch_webpage` tool when it needs to go deeper than search snippets, or when fetching JS-heavy pages.

### Interface (`tools/fetch/base.py`) — new

```python
class BaseFetchProvider(ABC):
    @abstractmethod
    def fetch(self, url: str) -> str | None:
        """Return page text/markdown, or None to fall through to next provider."""
        ...
```

### Implementations

#### `Crawl4AiFetchProvider` (`tools/fetch/crawl4ai.py`) — new, primary

```python
BrowserConfig(headless=True, enable_stealth=True, user_agent_mode="random")
CrawlerRunConfig(remove_overlay_elements=True, word_count_threshold=10)
```

- Returns `result.markdown.fit_markdown` — clean markdown optimised for LLMs
- Handles JS rendering, Cloudflare bypass, cookie banners
- Runs `asyncio.run()` for sync compatibility with the existing tool dispatch
- Timeout: 20s

#### `RequestsFetchProvider` (`tools/fetch/requests_fetch.py`) — fallback

- `requests` + BeautifulSoup, 10s timeout
- Detects Cloudflare challenge pages → returns `None`
- Used only when Crawl4AI is unavailable

### Chain (`tools/fetch/chain.py`) — new

```python
class FetchChain:
    def fetch(self, url: str) -> str:
        for provider in self.providers:
            result = provider.fetch(url)
            if result:
                return _truncate(result)  # 8,000 char cap
        return (
            f"Could not retrieve content from {url}. "
            "Use search snippets and training data to answer."
        )
```

Default chain: `[Crawl4AiFetchProvider, RequestsFetchProvider]`

`fetch/factory.py` builds the chain, gracefully skipping `Crawl4AiFetchProvider` if `crawl4ai` is not installed.

### `fetch_webpage.py` update

Replace the current layered `_fetch_requests` / `_fetch_amp_cache` / `_fetch_browser` logic with a single call to `FetchChain.fetch(url)`.

---

## Part 3 — Registry / Chat Service Changes

### `registry.py`

- Remove `web_search` tool from `get_tool_definitions()` and `get_system_prompts()`
- Keep `fetch_webpage` tool (our Crawl4AI chain)
- Native search tools are injected by the provider-specific chat adapter, not the registry

### Provider-level tool injection

Each LLM provider adapter (Anthropic, Gemini, OpenAI) injects the correct native search tool alongside `fetch_webpage`:

```
Anthropic request  →  tools: [web_search_20260209, fetch_webpage (ours)]
Gemini request     →  tools: [google_search_retrieval, fetch_webpage (ours)]
OpenAI request     →  tools: [web_search_preview, fetch_webpage (ours)]
```

Location to implement: wherever the LLM call is assembled per provider (likely `chat/streaming_service.py` or similar).

---

## What is NOT deleted yet

The following files stay in place until the new implementation is tested and confirmed working:

- `tools/web_search.py` (our custom DuckDuckGo search tool)
- `tools/search/` directory (DuckDuckGo, Tavily stubs, base)

They are kept as dead code during the transition and removed in a follow-up PR after end-to-end verification.

---

## File Summary

| Action | File |
|---|---|
| **Create** | `tools/fetch/base.py` |
| **Create** | `tools/fetch/crawl4ai.py` |
| **Create** | `tools/fetch/requests_fetch.py` |
| **Create** | `tools/fetch/chain.py` |
| **Create** | `tools/fetch/factory.py` |
| **Create** | `tools/fetch/__init__.py` |
| Modify | `tools/fetch_webpage.py` — use `FetchChain` |
| Modify | `tools/registry.py` — remove web_search, keep fetch_webpage |
| Modify | `chat/streaming_service.py` (or equivalent) — inject native search tool per provider |
| Modify | SSE streaming parser — handle `server_tool_use` + `web_search_tool_result` blocks |
| Modify | `core/config.py` — add `user_search_country` (default `"FR"`) |
| Modify | `pyproject.toml` — add `crawl4ai>=0.4` |
| **Keep (for now)** | `tools/web_search.py` |
| **Keep (for now)** | `tools/search/` directory |

---

## Dependencies

Add to `backend/pyproject.toml`:
```toml
"crawl4ai>=0.4",
```

`requests` and `beautifulsoup4` already present.
