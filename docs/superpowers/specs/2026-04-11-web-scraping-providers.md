# Web Scraping Providers — Design Spec

**Date:** 2026-04-11

---

## Goal

Replace the single-provider, ad-hoc web search and fetch implementations with clean multi-provider abstractions. Each abstraction has pluggable implementations selected via config, with automatic fallback when API keys are absent.

## Architecture

Two parallel provider hierarchies: one for **search**, one for **fetch**. Both are config-driven and fall back gracefully.

---

## Search Providers

### Interface

`BaseSearchProvider` already exists in `search/base.py`. Update the abstract method signature to include `region`:

```python
@abstractmethod
def search(self, query: str, num_results: int = 5, region: str = "uk-en") -> list[SearchResult]:
    ...
```

`SearchResult` dataclass stays unchanged: `title: str`, `url: str`, `snippet: str`.

### Implementations

#### `DuckDuckGoProvider` (`search/duckduckgo.py`) — existing, updated
- Uses `ddgs` / `duckduckgo_search` library
- Passes `region` to `ddgs.text()`
- Free, no API key, unreliable locale — used only as last-resort fallback

#### `BraveSearchProvider` (`search/brave.py`) — new
- Calls `https://api.search.brave.com/res/v1/web/search`
- Auth: `X-Subscription-Token: {BRAVE_SEARCH_API_KEY}` header
- Params: `q`, `count` (max 20), `country` derived from region (`uk-en` → `GB`, `us-en` → `US`, `wt-wt` → omitted)
- Maps response `web.results[].title/url/description` → `SearchResult`
- Free tier: 2,000 requests/month

#### `TavilyProvider` (`search/tavily.py`) — implement existing stub
- Calls `https://api.tavily.com/search` (POST)
- Auth: `api_key` in request body
- Params: `query`, `max_results`, `search_depth="advanced"`, `include_answer=False`
- Maps response `results[].title/url/content` → `SearchResult`
- Free tier: 1,000 requests/month

### Factory (`search/factory.py`)

```python
def get_search_provider() -> BaseSearchProvider:
    ...
```

Reads `settings.search_provider` (`SEARCH_PROVIDER` env var, default `"duckduckgo"`).

| Config value | Key required | Falls back to |
|---|---|---|
| `brave` | `BRAVE_SEARCH_API_KEY` | `duckduckgo` if key absent |
| `tavily` | `TAVILY_API_KEY` | `duckduckgo` if key absent |
| `duckduckgo` | — | — |

Logs a warning when falling back.

---

## Fetch Providers

### Interface (`fetch/base.py`) — new

```python
class BaseFetchProvider(ABC):
    @abstractmethod
    def fetch(self, url: str) -> str | None:
        """Return page text/markdown, or None if the provider cannot retrieve it."""
        ...
```

`None` means "try the next provider". A non-empty string is a success.

### Implementations

#### `Crawl4AiFetchProvider` (`fetch/crawl4ai.py`) — new
- Uses `crawl4ai.AsyncWebCrawler` with:
  - `BrowserConfig(headless=True, enable_stealth=True, user_agent_mode="random")`
  - `CrawlerRunConfig(remove_overlay_elements=True, word_count_threshold=10)`
- Returns `result.markdown.fit_markdown` (clean, LLM-optimised markdown)
- Runs async crawl inside `asyncio.run()` for sync compatibility
- Timeout: 20s
- Handles JS rendering, Cloudflare bypass, cookie banners

#### `JinaFetchProvider` (`fetch/jina.py`) — new
- `GET https://r.jina.ai/{url}` with header `Accept: text/plain`
- Uses `requests` with 15s timeout
- Free, no API key, returns clean markdown
- Handles many Cloudflare-protected sites without a browser

#### `RequestsFetchProvider` (`fetch/requests_fetch.py`) — extracted from existing code
- `requests` + `BeautifulSoup`
- 10s timeout
- Detects Cloudflare challenge pages (`"Just a moment"`, `"cf-browser-verification"`) → returns `None`
- Removes `script/style/nav/footer/header/aside` tags
- Lightest fallback for simple public pages

### Chain (`fetch/chain.py`) — new

```python
class FetchChain:
    def __init__(self, providers: list[BaseFetchProvider]):
        self.providers = providers

    def fetch(self, url: str) -> str:
        for provider in self.providers:
            result = provider.fetch(url)
            if result:
                return _truncate(result)
        return f"Could not retrieve content from {url} after all strategies failed. Use search snippets and training data to answer."
```

Default chain order: `[Crawl4AiFetchProvider, JinaFetchProvider, RequestsFetchProvider]`

A `fetch/factory.py` constructs the chain, skipping providers whose dependencies are not installed (e.g. `crawl4ai` not installed → skip silently, log warning).

---

## Config Changes

New fields in `core/config.py` (sourced from env vars):

```python
search_provider: str = "duckduckgo"   # brave | tavily | duckduckgo
brave_search_api_key: str = ""
tavily_api_key: str = ""
```

---

## Integration Points

### `web_search.py`
- `execute()` calls `get_search_provider()` instead of directly instantiating `DuckDuckGoProvider`
- Language filtering (`_is_english_result`) stays in place — applied after any provider returns results
- Region parameter flows through unchanged

### `fetch_webpage.py`
- `execute()` calls `FetchChain.fetch(url)` (constructed via `fetch/factory.py`)
- All three strategy functions (`_fetch_requests`, `_fetch_amp_cache`, `_fetch_browser`) are replaced by the provider chain
- Google AMP cache strategy is dropped (Crawl4AI + Jina cover its use cases more reliably)

---

## Dependencies

Add to `backend/pyproject.toml`:

```toml
"crawl4ai>=0.4",
"tavily-python>=0.5",
```

`requests` and `beautifulsoup4` already added in the previous session.
`brave` uses plain `requests` — no extra package needed.

---

## File Summary

| Action | File |
|---|---|
| Modify | `tools/search/base.py` — add `region` to abstract method |
| Modify | `tools/search/duckduckgo.py` — signature already correct |
| **Create** | `tools/search/brave.py` |
| **Create** | `tools/search/factory.py` |
| Modify | `tools/search/tavily.py` — implement stub |
| **Create** | `tools/fetch/base.py` |
| **Create** | `tools/fetch/crawl4ai.py` |
| **Create** | `tools/fetch/jina.py` |
| **Create** | `tools/fetch/requests_fetch.py` |
| **Create** | `tools/fetch/chain.py` |
| **Create** | `tools/fetch/factory.py` |
| Modify | `tools/web_search.py` — use `get_search_provider()` |
| Modify | `tools/fetch_webpage.py` — use `FetchChain` |
| Modify | `core/config.py` — add `search_provider`, `brave_search_api_key`, `tavily_api_key` |
| Modify | `pyproject.toml` — add `crawl4ai`, `tavily-python` |
