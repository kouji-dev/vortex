# Built-in Tools: Web Search & Structured Data Query — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `web_search` (DuckDuckGo, swappable) and `query_structured_data` (pandas + LLM) as user-activatable tool capabilities in the chat system.

**Architecture:** A new `tools/` module holds a `BaseSearchProvider` abstraction, `DuckDuckGoProvider`, and a `query_structured_data` function. A `ToolRegistry` centralises dispatch. `conversations.py` wires the new tools into the existing tool-call loop and capability toggle system with minimal changes.

**Tech Stack:** Python 3.12, FastAPI, `duckduckgo-search`, `pandas`, existing `llm_svc`, pytest.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `backend/src/ai_portal/tools/__init__.py` | Package marker |
| Create | `backend/src/ai_portal/tools/registry.py` | `ToolRegistry.dispatch(name, args) → dict` |
| Create | `backend/src/ai_portal/tools/search/__init__.py` | Package marker |
| Create | `backend/src/ai_portal/tools/search/base.py` | `SearchResult` dataclass + `BaseSearchProvider` ABC |
| Create | `backend/src/ai_portal/tools/search/duckduckgo.py` | `DuckDuckGoProvider` |
| Create | `backend/src/ai_portal/tools/search/tavily.py` | `TavilyProvider` stub |
| Create | `backend/src/ai_portal/tools/data/__init__.py` | Package marker |
| Create | `backend/src/ai_portal/tools/data/query.py` | `query_structured_data(data, question) → str` |
| Modify | `backend/src/ai_portal/schemas/conversation_settings.py` | Add `web_search`, `data_query` to `CapabilityToggles` |
| Modify | `backend/src/ai_portal/api/conversations.py` | Wire tools into `tools[]`, `_dispatch_tool_call`, `_capability_instructions`, `CapabilityProfileRead` |
| Modify | `backend/pyproject.toml` | Add `duckduckgo-search`, `pandas` dependencies |
| Create | `backend/tests/test_search_providers.py` | Unit tests for `DuckDuckGoProvider` |
| Create | `backend/tests/test_data_query.py` | Unit tests for `query_structured_data` |
| Create | `backend/tests/test_tool_registry.py` | Unit tests for `ToolRegistry.dispatch` |
| Create | `backend/tests/test_builtin_tools_e2e.py` | E2E tests for web_search and data_query tool-call loop |

---

## Task 1: Add dependencies

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add `duckduckgo-search` and `pandas` to dependencies**

Open `backend/pyproject.toml`. In the `dependencies` list, add after `"chonkie[semantic,code]>=1.0"`:

```toml
  "duckduckgo-search>=6.0",
  "pandas>=2.0",
```

- [ ] **Step 2: Install the new dependencies**

```bash
cd backend && pip install -e ".[dev]"
```

Expected: installs without errors, `duckduckgo_search` and `pandas` importable.

- [ ] **Step 3: Verify imports work**

```bash
python -c "from duckduckgo_search import DDGS; import pandas; print('ok')"
```

Expected output: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml
git commit -m "chore: add duckduckgo-search and pandas dependencies"
```

---

## Task 2: `SearchResult` dataclass and `BaseSearchProvider` ABC

**Files:**
- Create: `backend/src/ai_portal/tools/__init__.py`
- Create: `backend/src/ai_portal/tools/search/__init__.py`
- Create: `backend/src/ai_portal/tools/search/base.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_search_providers.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_search_providers.py -v
```

Expected: `ModuleNotFoundError` — `ai_portal.tools` does not exist yet.

- [ ] **Step 3: Create package markers and base module**

Create `backend/src/ai_portal/tools/__init__.py` (empty):
```python
```

Create `backend/src/ai_portal/tools/search/__init__.py` (empty):
```python
```

Create `backend/src/ai_portal/tools/search/base.py`:
```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class BaseSearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        """Search and return up to num_results results."""
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_search_providers.py -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/src/ai_portal/tools/ backend/tests/test_search_providers.py
git commit -m "feat: add SearchResult dataclass and BaseSearchProvider ABC"
```

---

## Task 3: `DuckDuckGoProvider`

**Files:**
- Create: `backend/src/ai_portal/tools/search/duckduckgo.py`
- Modify: `backend/tests/test_search_providers.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_search_providers.py`:

```python
from unittest.mock import MagicMock, patch


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_search_providers.py -v -k "duckduckgo"
```

Expected: `ModuleNotFoundError` for `duckduckgo`.

- [ ] **Step 3: Implement `DuckDuckGoProvider`**

Create `backend/src/ai_portal/tools/search/duckduckgo.py`:

```python
from __future__ import annotations

import logging

from duckduckgo_search import DDGS

from ai_portal.tools.search.base import BaseSearchProvider, SearchResult

logger = logging.getLogger(__name__)

_TIMEOUT = 10  # seconds


class DuckDuckGoProvider(BaseSearchProvider):
    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        try:
            with DDGS(timeout=_TIMEOUT) as ddgs:
                raw = ddgs.text(query, max_results=min(num_results, 10))
            return [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", ""),
                    snippet=r.get("body", ""),
                )
                for r in (raw or [])
            ]
        except Exception:
            logger.exception("duckduckgo_search_failed")
            return []
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_search_providers.py -v
```

Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/src/ai_portal/tools/search/duckduckgo.py backend/tests/test_search_providers.py
git commit -m "feat: implement DuckDuckGoProvider"
```

---

## Task 4: `TavilyProvider` stub

**Files:**
- Create: `backend/src/ai_portal/tools/search/tavily.py`

- [ ] **Step 1: Create the stub**

Create `backend/src/ai_portal/tools/search/tavily.py`:

```python
from __future__ import annotations

from ai_portal.tools.search.base import BaseSearchProvider, SearchResult


class TavilyProvider(BaseSearchProvider):
    """Stub — wire up when Tavily API key is available."""

    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        raise NotImplementedError("TavilyProvider is not yet configured.")
```

- [ ] **Step 2: Commit**

```bash
git add backend/src/ai_portal/tools/search/tavily.py
git commit -m "feat: add TavilyProvider stub"
```

---

## Task 5: `query_structured_data`

**Files:**
- Create: `backend/src/ai_portal/tools/data/__init__.py`
- Create: `backend/src/ai_portal/tools/data/query.py`
- Create: `backend/tests/test_data_query.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_data_query.py`:

```python
from unittest.mock import patch


def test_query_csv_data():
    csv_data = "name,age\nAlice,30\nBob,25\nCharlie,35"
    question = "What is the average age?"

    with patch("ai_portal.tools.data.query.llm_svc.chat_completions_stream_deltas") as mock_llm:
        mock_llm.return_value = iter(["The average age is 30.0"])
        from ai_portal.tools.data.query import query_structured_data
        result = query_structured_data(csv_data, question)

    assert "30" in result
    # Verify LLM was called with data context
    call_messages = mock_llm.call_args[0][0]
    system_msg = call_messages[0]["content"]
    assert "name" in system_msg
    assert "age" in system_msg
    assert question in call_messages[1]["content"]


def test_query_json_data():
    json_data = '[{"product": "A", "sales": 100}, {"product": "B", "sales": 200}]'
    question = "Which product has higher sales?"

    with patch("ai_portal.tools.data.query.llm_svc.chat_completions_stream_deltas") as mock_llm:
        mock_llm.return_value = iter(["Product B has higher sales with 200."])
        from ai_portal.tools.data.query import query_structured_data
        result = query_structured_data(json_data, question)

    assert "B" in result


def test_query_unparseable_data():
    from ai_portal.tools.data.query import query_structured_data
    result = query_structured_data("this is not csv or json !!!###", "what?")
    assert "Could not parse" in result


def test_query_returns_error_on_llm_failure():
    csv_data = "x,y\n1,2\n3,4"
    with patch("ai_portal.tools.data.query.llm_svc.chat_completions_stream_deltas") as mock_llm:
        mock_llm.side_effect = Exception("LLM error")
        from ai_portal.tools.data.query import query_structured_data
        result = query_structured_data(csv_data, "sum of x?")
    assert "Could not answer" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_data_query.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create package marker**

Create `backend/src/ai_portal/tools/data/__init__.py` (empty):
```python
```

- [ ] **Step 4: Implement `query_structured_data`**

Create `backend/src/ai_portal/tools/data/query.py`:

```python
from __future__ import annotations

import io
import json
import logging

import pandas as pd

from ai_portal.services import llm as llm_svc

logger = logging.getLogger(__name__)

_SAMPLE_ROWS = 20


def query_structured_data(data: str, question: str) -> str:
    """Parse CSV or JSON data and answer a question about it using the LLM."""
    df = _parse(data.strip())
    if df is None:
        return "Could not parse the provided data. Ensure it is valid CSV or JSON."

    schema = _describe(df)
    sample = df.head(_SAMPLE_ROWS).to_csv(index=False)

    system_prompt = (
        "You are a data analyst. The user has provided structured data. "
        "Answer the question accurately using only the data shown.\n\n"
        f"Schema:\n{schema}\n\n"
        f"Data sample (up to {_SAMPLE_ROWS} rows):\n{sample}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    try:
        chunks = list(llm_svc.chat_completions_stream_deltas(messages))
        return "".join(chunks)
    except Exception:
        logger.exception("data_query_llm_failed")
        return "Could not answer the question due to an internal error."


def _parse(data: str) -> pd.DataFrame | None:
    # Try JSON first
    try:
        parsed = json.loads(data)
        if isinstance(parsed, list):
            return pd.DataFrame(parsed)
        if isinstance(parsed, dict):
            return pd.DataFrame([parsed])
    except (json.JSONDecodeError, ValueError):
        pass

    # Try CSV
    try:
        return pd.read_csv(io.StringIO(data))
    except Exception:
        pass

    return None


def _describe(df: pd.DataFrame) -> str:
    lines = [f"Columns ({len(df.columns)}): {', '.join(df.columns)}"]
    lines.append(f"Rows: {len(df)}")
    for col in df.columns:
        dtype = str(df[col].dtype)
        lines.append(f"  - {col} ({dtype})")
    return "\n".join(lines)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_data_query.py -v
```

Expected: 4 PASSED.

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/tools/data/ backend/tests/test_data_query.py
git commit -m "feat: implement query_structured_data tool"
```

---

## Task 6: `ToolRegistry`

**Files:**
- Create: `backend/src/ai_portal/tools/registry.py`
- Create: `backend/tests/test_tool_registry.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_tool_registry.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_tool_registry.py -v
```

Expected: `ModuleNotFoundError` for `registry`.

- [ ] **Step 3: Implement `ToolRegistry`**

Create `backend/src/ai_portal/tools/registry.py`:

```python
from __future__ import annotations

import logging

from ai_portal.tools.data.query import query_structured_data
from ai_portal.tools.search.duckduckgo import DuckDuckGoProvider

logger = logging.getLogger(__name__)


class ToolRegistry:
    def dispatch(self, name: str, args: dict) -> dict:
        if name == "web_search":
            return self._web_search(args)
        if name == "query_structured_data":
            return self._query_structured_data(args)
        return {"role": "tool", "name": name, "content": f"Error: unknown tool '{name}'"}

    def _web_search(self, args: dict) -> dict:
        query = args.get("query", "")
        num_results = int(args.get("num_results", 5))
        provider = DuckDuckGoProvider()
        results = provider.search(query, num_results=num_results)
        if not results:
            content = "Web search returned no results for this query."
        else:
            lines = []
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. [{r.title}]({r.url})\n   {r.snippet}")
            content = "\n\n".join(lines)
        return {"role": "tool", "name": "web_search", "content": content}

    def _query_structured_data(self, args: dict) -> dict:
        data = args.get("data", "")
        question = args.get("question", "")
        content = query_structured_data(data, question)
        return {"role": "tool", "name": "query_structured_data", "content": content}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_tool_registry.py -v
```

Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/src/ai_portal/tools/registry.py backend/tests/test_tool_registry.py
git commit -m "feat: implement ToolRegistry with web_search and query_structured_data dispatch"
```

---

## Task 7: Extend `CapabilityToggles` with new fields

**Files:**
- Modify: `backend/src/ai_portal/schemas/conversation_settings.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_conversations_api.py` (find the existing `test_create_conversation_defaults_model_and_settings` test and note the expected settings shape — we will update it after implementation):

Actually, add a new test file to avoid touching existing passing tests:

```python
# backend/tests/test_capability_toggles.py
from ai_portal.schemas.conversation_settings import CapabilityToggles, ConversationSettings


def test_capability_toggles_has_new_fields():
    cap = CapabilityToggles()
    assert cap.web_search is False
    assert cap.data_query is False


def test_capability_toggles_accepts_new_fields():
    cap = CapabilityToggles(web_search=True, data_query=True)
    assert cap.web_search is True
    assert cap.data_query is True


def test_conversation_settings_roundtrip_with_new_fields():
    settings = ConversationSettings(
        capabilities=CapabilityToggles(web_search=True, data_query=False)
    )
    dumped = settings.model_dump()
    reloaded = ConversationSettings(**dumped)
    assert reloaded.capabilities.web_search is True
    assert reloaded.capabilities.data_query is False
```

Save to `backend/tests/test_capability_toggles.py`.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_capability_toggles.py -v
```

Expected: `ValidationError` — `web_search` is not a valid field (extra='forbid').

- [ ] **Step 3: Add fields to `CapabilityToggles`**

Edit `backend/src/ai_portal/schemas/conversation_settings.py`. Change the class to:

```python
class CapabilityToggles(BaseModel):
    """Feature toggles for a conversation (reflection / research / web / web_search / data_query)."""

    model_config = ConfigDict(extra="forbid")

    reflection: bool = False
    research: bool = False
    web: bool = False
    web_search: bool = False
    data_query: bool = False
```

- [ ] **Step 4: Update the existing default-settings test**

The test `test_create_conversation_defaults_model_and_settings` in `backend/tests/test_conversations_api.py` asserts:
```python
assert body["settings"] == {
    "capabilities": {"reflection": False, "research": False, "web": False},
}
```
This will now fail because the response includes the new fields. Update the assertion to:
```python
assert body["settings"] == {
    "capabilities": {
        "reflection": False,
        "research": False,
        "web": False,
        "web_search": False,
        "data_query": False,
    },
}
```

- [ ] **Step 5: Run all capability and conversation tests**

```bash
cd backend && python -m pytest tests/test_capability_toggles.py tests/test_conversations_api.py -v
```

Expected: all PASSED (postgres-gated tests skip if no DB).

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/schemas/conversation_settings.py \
        backend/tests/test_capability_toggles.py \
        backend/tests/test_conversations_api.py
git commit -m "feat: add web_search and data_query capability toggles"
```

---

## Task 8: Wire tools into `conversations.py`

**Files:**
- Modify: `backend/src/ai_portal/api/conversations.py`

This task has four sub-changes. Make them all before running tests.

- [ ] **Step 1: Add import at top of `conversations.py`**

After the existing imports, add:

```python
from ai_portal.tools.registry import ToolRegistry

_tool_registry = ToolRegistry()
```

- [ ] **Step 2: Add tool schemas to the `tools[]` list in `stream_message`**

Find the block starting at line ~710 (`tools: list[dict[str, Any]] = []`). After the existing `if kb_ids:` block that populates `tools`, add:

```python
    cap = conv.settings.capabilities if conv.settings else None
    if cap and cap.web_search:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": (
                        "Search the web for current information. Use when the user asks about "
                        "recent events, facts you are unsure about, or anything requiring "
                        "up-to-date data."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The search query"},
                            "num_results": {
                                "type": "integer",
                                "description": "Number of results to return. Default 5, max 10.",
                            },
                        },
                        "required": ["query"],
                    },
                },
            }
        )
    if cap and cap.data_query:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "query_structured_data",
                    "description": (
                        "Answer questions about structured data (CSV, JSON, or table) "
                        "the user has provided in the conversation. Use for aggregations, "
                        "filtering, lookups, or comparisons."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "string",
                                "description": "The raw CSV, JSON, or table content to analyze",
                            },
                            "question": {
                                "type": "string",
                                "description": "The question to answer about the data",
                            },
                        },
                        "required": ["data", "question"],
                    },
                },
            }
        )
```

- [ ] **Step 3: Add dispatch cases to `_dispatch_tool_call`**

Find `_dispatch_tool_call`. After the `if name == "search_knowledge_base":` block and before the final `return` line, add:

```python
    if name in ("web_search", "query_structured_data"):
        return _tool_registry.dispatch(name, args)
```

- [ ] **Step 4: Add capability instructions for new tools**

In `_capability_instructions`, after the existing `if cap.web:` block, add:

```python
    if cap.web_search:
        parts.append(
            "Web search: you have access to the web_search tool. "
            "Use it to find current information when needed."
        )
    if cap.data_query:
        parts.append(
            "Data analysis: you have access to the query_structured_data tool. "
            "Use it when the user shares CSV, JSON, or table data and asks questions about it."
        )
```

- [ ] **Step 5: Add new entries to `CapabilityProfileRead`**

Find the `CapabilityProfileRead` class and `get_capability_profile` endpoint. Update:

```python
class CapabilityProfileRead(BaseModel):
    reflection: CapabilityProfileEntryRead
    research: CapabilityProfileEntryRead
    web: CapabilityProfileEntryRead
    web_search: CapabilityProfileEntryRead
    data_query: CapabilityProfileEntryRead


@router.get("/capability-profile", response_model=CapabilityProfileRead)
def get_capability_profile(
    _user: Annotated[User, Depends(get_current_user)],
) -> CapabilityProfileRead:
    """UI copy for chat capability toggles (Add options menu)."""
    return CapabilityProfileRead(
        reflection=CapabilityProfileEntryRead(
            description=(
                "Note key assumptions and uncertainties before answering; adjust if you spot gaps."
            )
        ),
        research=CapabilityProfileEntryRead(
            description=(
                "Separate known facts from what would need verification; suggest concrete checks "
                "or sources the user could use."
            )
        ),
        web=CapabilityProfileEntryRead(
            description=(
                "No live web search is configured. If the answer depends on current events or "
                "post-training facts, say so and suggest how the user can verify."
            )
        ),
        web_search=CapabilityProfileEntryRead(
            description="Search the web in real time to answer questions about current events or recent information."
        ),
        data_query=CapabilityProfileEntryRead(
            description="Analyse CSV, JSON, or table data you share in the conversation."
        ),
    )
```

- [ ] **Step 6: Run existing dispatch tests**

```bash
cd backend && python -m pytest tests/test_rag_toolcall_loop.py -v
```

Expected: all PASSED — existing RAG dispatch still works.

- [ ] **Step 7: Commit**

```bash
git add backend/src/ai_portal/api/conversations.py
git commit -m "feat: wire web_search and data_query tools into conversation stream"
```

---

## Task 9: E2E tests

**Files:**
- Create: `backend/tests/test_builtin_tools_e2e.py`

- [ ] **Step 1: Write the E2E tests**

Create `backend/tests/test_builtin_tools_e2e.py`:

```python
"""
E2E tests for web_search and query_structured_data tools.

These tests verify the full SSE streaming path:
  - Tool schemas are sent to the LLM when capabilities are enabled
  - tool_call SSE events are emitted
  - tool results feed back into the final reply

DuckDuckGo and the LLM are mocked. Postgres required for conversation creation.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ai_portal.main import app
from tests.conftest import requires_postgres

client = TestClient(app)
AUTH = {"Authorization": "Bearer devtoken"}


def _parse_sse(raw: str) -> list[dict]:
    events = []
    for line in raw.strip().splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


def _make_stream_pieces(tool_name: str, tool_args: dict, reply: str):
    """Yields pieces simulating: tool call → reply."""
    yield {"type": "tool_call", "tool_call": {"name": tool_name, "arguments": json.dumps(tool_args)}}
    yield {"type": "delta", "text": reply}


@requires_postgres
def test_web_search_tool_called_and_reply_streamed():
    # Create conversation with web_search enabled
    r = client.post(
        "/api/chat/conversations",
        headers=AUTH,
        json={"settings": {"capabilities": {"web_search": True}}},
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    stream_pieces = [
        {"type": "tool_call", "tool_call": {"name": "web_search", "arguments": '{"query": "latest Python release"}'}},
        {"type": "delta", "text": "Python 3.13 was released in October 2024."},
    ]

    with patch("ai_portal.api.conversations.llm_svc.chat_completions_stream_with_tools") as mock_stream, \
         patch("ai_portal.tools.registry.DuckDuckGoProvider") as MockDDG:
        mock_stream.return_value = iter(stream_pieces)
        instance = MagicMock()
        from ai_portal.tools.search.base import SearchResult
        instance.search.return_value = [
            SearchResult(title="Python 3.13", url="https://python.org", snippet="Released Oct 2024")
        ]
        MockDDG.return_value = instance

        resp = client.post(
            f"/api/chat/conversations/{cid}/messages/stream",
            headers=AUTH,
            json={"content": "What is the latest Python release?"},
        )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    tool_call_events = [e for e in events if e.get("type") == "tool_call"]
    assert len(tool_call_events) >= 1
    assert tool_call_events[0]["name"] == "web_search"


@requires_postgres
def test_web_search_result_referenced_in_reply():
    r = client.post(
        "/api/chat/conversations",
        headers=AUTH,
        json={"settings": {"capabilities": {"web_search": True}}},
    )
    assert r.status_code == 201
    cid = r.json()["id"]

    # Second LLM call (after tool result injected) returns the final reply
    call_count = 0

    def fake_stream(messages, model=None, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            yield {"type": "tool_call", "tool_call": {"name": "web_search", "arguments": '{"query": "openai news"}'}}
        else:
            yield {"type": "delta", "text": "Based on search results: OpenAI released GPT-5."}

    with patch("ai_portal.api.conversations.llm_svc.chat_completions_stream_with_tools", side_effect=fake_stream), \
         patch("ai_portal.tools.registry.DuckDuckGoProvider") as MockDDG:
        instance = MagicMock()
        from ai_portal.tools.search.base import SearchResult
        instance.search.return_value = [
            SearchResult(title="OpenAI GPT-5", url="https://openai.com", snippet="GPT-5 launched.")
        ]
        MockDDG.return_value = instance

        resp = client.post(
            f"/api/chat/conversations/{cid}/messages/stream",
            headers=AUTH,
            json={"content": "What's new at OpenAI?"},
        )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    delta_text = "".join(e.get("text", "") for e in events if e.get("type") == "delta")
    assert "GPT-5" in delta_text


@requires_postgres
def test_data_query_tool_called():
    r = client.post(
        "/api/chat/conversations",
        headers=AUTH,
        json={"settings": {"capabilities": {"data_query": True}}},
    )
    assert r.status_code == 201
    cid = r.json()["id"]

    stream_pieces = [
        {"type": "tool_call", "tool_call": {
            "name": "query_structured_data",
            "arguments": '{"data": "name,score\\nAlice,90\\nBob,80", "question": "Who has the highest score?"}',
        }},
        {"type": "delta", "text": "Alice has the highest score with 90."},
    ]

    with patch("ai_portal.api.conversations.llm_svc.chat_completions_stream_with_tools") as mock_stream, \
         patch("ai_portal.tools.data.query.llm_svc.chat_completions_stream_deltas") as mock_data_llm:
        mock_stream.return_value = iter(stream_pieces)
        mock_data_llm.return_value = iter(["Alice has the highest score with 90."])

        resp = client.post(
            f"/api/chat/conversations/{cid}/messages/stream",
            headers=AUTH,
            json={"content": "name,score\nAlice,90\nBob,80\n\nWho has the highest score?"},
        )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    tool_call_events = [e for e in events if e.get("type") == "tool_call"]
    assert any(e["name"] == "query_structured_data" for e in tool_call_events)


@requires_postgres
def test_data_query_result_in_reply():
    r = client.post(
        "/api/chat/conversations",
        headers=AUTH,
        json={"settings": {"capabilities": {"data_query": True}}},
    )
    assert r.status_code == 201
    cid = r.json()["id"]

    call_count = 0

    def fake_stream(messages, model=None, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            yield {"type": "tool_call", "tool_call": {
                "name": "query_structured_data",
                "arguments": '{"data": "x,y\\n1,2\\n3,4", "question": "what is the sum of x?"}',
            }}
        else:
            yield {"type": "delta", "text": "The sum of x is 4."}

    with patch("ai_portal.api.conversations.llm_svc.chat_completions_stream_with_tools", side_effect=fake_stream), \
         patch("ai_portal.tools.data.query.llm_svc.chat_completions_stream_deltas") as mock_data_llm:
        mock_data_llm.return_value = iter(["The sum of x is 4."])

        resp = client.post(
            f"/api/chat/conversations/{cid}/messages/stream",
            headers=AUTH,
            json={"content": "x,y\n1,2\n3,4\n\nWhat is the sum of x?"},
        )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    delta_text = "".join(e.get("text", "") for e in events if e.get("type") == "delta")
    assert "4" in delta_text


@requires_postgres
def test_tools_off_by_default():
    """When no capabilities are enabled, no tool schemas should be sent to the LLM."""
    r = client.post("/api/chat/conversations", headers=AUTH, json={})
    assert r.status_code == 201
    cid = r.json()["id"]

    captured_tools = []

    def fake_stream(messages, model=None, tools=None):
        captured_tools.append(tools)
        yield {"type": "delta", "text": "Hello!"}

    with patch("ai_portal.api.conversations.llm_svc.chat_completions_stream_with_tools", side_effect=fake_stream):
        resp = client.post(
            f"/api/chat/conversations/{cid}/messages/stream",
            headers=AUTH,
            json={"content": "hi"},
        )

    assert resp.status_code == 200
    # tools should be None or empty when no capabilities enabled and no KB attached
    assert captured_tools[0] is None or captured_tools[0] == []


def test_capability_profile_includes_new_tools():
    """The capability profile endpoint exposes web_search and data_query entries."""
    r = client.get("/api/chat/capability-profile", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert "web_search" in body
    assert "data_query" in body
    assert body["web_search"]["description"]
    assert body["data_query"]["description"]
```

- [ ] **Step 2: Run tests to verify they fail (for the right reason)**

```bash
cd backend && python -m pytest tests/test_builtin_tools_e2e.py::test_capability_profile_includes_new_tools tests/test_builtin_tools_e2e.py::test_tools_off_by_default -v
```

`test_capability_profile_includes_new_tools` should FAIL (key missing from response).
`test_tools_off_by_default` should PASS or SKIP (it tests existing behaviour).

- [ ] **Step 3: Run all E2E tests (after Task 8 is complete)**

```bash
cd backend && python -m pytest tests/test_builtin_tools_e2e.py -v
```

Expected: all tests PASS or SKIP (postgres-gated ones skip without DB).

- [ ] **Step 4: Run full test suite to confirm no regressions**

```bash
cd backend && python -m pytest tests/ -v
```

Expected: all previously passing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_builtin_tools_e2e.py
git commit -m "test: add E2E tests for web_search and data_query tool capabilities"
```

---

## Task 10: Final integration check

- [ ] **Step 1: Run the full test suite one more time**

```bash
cd backend && python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: no new failures.

- [ ] **Step 2: Verify the tools module is importable cleanly**

```bash
python -c "
from ai_portal.tools.registry import ToolRegistry
from ai_portal.tools.search.base import BaseSearchProvider, SearchResult
from ai_portal.tools.search.duckduckgo import DuckDuckGoProvider
from ai_portal.tools.search.tavily import TavilyProvider
from ai_portal.tools.data.query import query_structured_data
print('all imports ok')
"
```

Expected: `all imports ok`

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: built-in tools — web_search (DuckDuckGo) and query_structured_data"
```
