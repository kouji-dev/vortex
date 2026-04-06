# Built-in Tools: Web Search & Structured Data Query

**Date:** 2026-04-06  
**Status:** Approved

---

## Overview

Add two user-activatable tools to the chat system: `web_search` (DuckDuckGo now, Tavily later) and `query_structured_data` (pandas-based). Both are off by default and enabled via capability toggles per conversation, consistent with the existing `reflection` and `research` toggles.

---

## New Files

```
backend/src/ai_portal/
└── tools/
    ├── __init__.py
    ├── registry.py              # ToolRegistry.dispatch(name, args, context) → dict
    ├── search/
    │   ├── __init__.py
    │   ├── base.py              # BaseSearchProvider (abstract)
    │   ├── duckduckgo.py        # DuckDuckGoProvider
    │   └── tavily.py            # TavilyProvider (stub, not wired)
    └── data/
        ├── __init__.py
        └── query.py             # query_structured_data(data, question) → str
```

---

## Changed Files

- `backend/src/ai_portal/api/conversations.py`
  - `CapabilitySettings`: add `web_search: bool = False`, `data_query: bool = False`
  - `_build_capability_instructions`: add tool-use instructions when enabled
  - `stream_message`: append tool schemas to `tools[]` when capabilities are on
  - `_dispatch_tool_call`: add `web_search` and `query_structured_data` cases delegating to `registry.dispatch`
  - `/api/chat/capabilities` endpoint: add two new capability entries

---

## Tool Schemas (sent to LLM)

### web_search
```json
{
  "name": "web_search",
  "description": "Search the web for current information. Use when the user asks about recent events, facts you are unsure about, or anything requiring up-to-date data.",
  "parameters": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "The search query" },
      "num_results": { "type": "integer", "description": "Number of results to return. Default 5, max 10." }
    },
    "required": ["query"]
  }
}
```

### query_structured_data
```json
{
  "name": "query_structured_data",
  "description": "Answer questions about structured data (CSV, JSON, or table) the user has provided in the conversation. Use for aggregations, filtering, lookups, or comparisons.",
  "parameters": {
    "type": "object",
    "properties": {
      "data": { "type": "string", "description": "The raw CSV, JSON, or table content to analyze" },
      "question": { "type": "string", "description": "The question to answer about the data" }
    },
    "required": ["data", "question"]
  }
}
```

---

## Data Flow

1. User enables web search or data query toggle → `capabilities` field on `ChatConversation.settings` updated
2. On next `stream_message`, enabled tool schemas are appended to `tools[]` sent to LLM
3. LLM emits a tool call → `tool_call_buffer` captured in the streaming loop
4. `_dispatch_tool_call` calls `registry.dispatch(name, args)`
5. Registry routes to `DuckDuckGoProvider.search()` or `query_structured_data()`
6. Result returned as readable text, appended as `role: tool` message
7. Loop continues — LLM reads result and writes final answer, streamed as SSE to frontend

---

## Tool Implementations

### web_search
- `BaseSearchProvider`: abstract class with `search(query: str, num_results: int) -> list[SearchResult]`
- `SearchResult`: dataclass with `title: str`, `url: str`, `snippet: str`
- `DuckDuckGoProvider`: wraps `duckduckgo_search` pip package, 10s timeout
- `TavilyProvider`: stub raising `NotImplementedError`, ready for future wiring
- `ToolRegistry` formats results as numbered list: `1. [Title](url)\n   snippet`

### query_structured_data
- Accepts raw CSV or JSON string + a natural language question
- Parses data with `pandas` (CSV via `read_csv`, JSON via `read_json`)
- Passes parsed schema summary + data sample + question to the LLM (fast model) for answering
- Returns the LLM's answer as a string
- Does not execute arbitrary code — LLM reads data and answers directly

---

## Error Handling

| Scenario | Behavior |
|---|---|
| DuckDuckGo rate-limited / timeout | Return `"Web search temporarily unavailable. Please try again shortly."` |
| Unparseable data in query_structured_data | Return `"Could not parse the provided data. Ensure it is valid CSV or JSON."` |
| Unknown tool name in registry | Return `"Unknown tool."` — no crash |
| All errors | Logged via `logger.exception`, never bubble up to 500 |

All tools enforce a 10s timeout in the provider layer.

---

## Capability Toggles

Both tools follow the existing capability pattern:
- Off by default
- Stored in `conversation.settings.capabilities`
- Shown in the frontend "Add options" menu alongside reflection/research
- Capability profile endpoint returns descriptions for UI rendering

---

## E2E Tests

| Test | Verifies |
|---|---|
| `test_web_search_tool_called` | With capability on, SSE stream includes `{"type": "tool_call", "name": "web_search"}` |
| `test_web_search_result_in_reply` | Final reply references content from mocked search results |
| `test_data_query_tool_called` | With CSV in message, SSE stream includes `{"type": "tool_call", "name": "query_structured_data"}` |
| `test_data_query_result_correct` | Reply contains expected value derived from the data |
| `test_tools_off_by_default` | Without enabling toggles, no tool schemas sent; no tool_call events emitted |
| `test_duckduckgo_provider_unit` | `DuckDuckGoProvider.search()` returns `list[SearchResult]` with correct fields (integration, marked `@pytest.mark.integration`) |

DuckDuckGo is mocked in E2E tests. Real network calls only in `@pytest.mark.integration` tests.

---

## Dependencies

- `duckduckgo-search` — add to `backend/pyproject.toml`
- `pandas` — likely already present (used in ingest); confirm before adding
- No new DB migrations required
