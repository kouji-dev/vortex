"""Phase I — RAG memory.search tool."""
from __future__ import annotations

import inspect

from ai_portal.memory import rag_tool


def test_tool_definition_shape() -> None:
    td = rag_tool.TOOL_DEFINITION
    assert td["name"] == "memory.search"
    assert "input_schema" in td
    schema = td["input_schema"]
    assert "query" in schema["properties"]
    assert "top_k" in schema["properties"]
    assert "query" in schema["required"]


def test_execute_is_coroutine() -> None:
    assert inspect.iscoroutinefunction(rag_tool.execute)


def test_register_returns_bool() -> None:
    # No-op when no RAG registry — must not raise.
    out = rag_tool.register_with_rag()
    assert isinstance(out, bool)
