import json
from unittest.mock import MagicMock, patch

from ai_portal.chat.service import _dispatch_tool_call


def test_tool_call_search_dispatches():
    db = MagicMock()
    tool_call = {
        "name": "search_knowledge_base",
        "arguments": json.dumps({"query": "auth", "kb_ids": [1]}),
    }
    with patch("ai_portal.chat.service.rag_svc.search_knowledge_base_tool") as m:
        m.return_value = {"context": "ctx", "used_kbs": [], "citations": []}
        result = _dispatch_tool_call(db, tool_call, kb_ids=[1])
    assert result["content"] == "ctx"
    assert result["role"] == "tool"
    assert result["name"] == "search_knowledge_base"


def test_unknown_tool_returns_error():
    db = MagicMock()
    result = _dispatch_tool_call(db, {"name": "nope", "arguments": "{}"}, kb_ids=[])
    assert "unknown tool" in result["content"].lower()
    assert result["role"] == "tool"


def test_tool_call_with_malformed_arguments():
    db = MagicMock()
    tool_call = {
        "name": "search_knowledge_base",
        "arguments": "not valid json",
    }
    with patch("ai_portal.chat.service.rag_svc.search_knowledge_base_tool") as m:
        m.return_value = {"context": "", "used_kbs": [], "citations": []}
        result = _dispatch_tool_call(db, tool_call, kb_ids=[1])
    assert result["role"] == "tool"
    m.assert_called_once_with(db=db, query="", kb_ids=[1], top_k=None)


def test_tool_call_uses_kb_ids_fallback():
    """When the LLM omits kb_ids in args, fall back to conversation kb_ids."""
    db = MagicMock()
    tool_call = {
        "name": "search_knowledge_base",
        "arguments": json.dumps({"query": "test"}),
    }
    with patch("ai_portal.chat.service.rag_svc.search_knowledge_base_tool") as m:
        m.return_value = {"context": "found", "used_kbs": [], "citations": []}
        result = _dispatch_tool_call(db, tool_call, kb_ids=[2, 3])
    m.assert_called_once_with(db=db, query="test", kb_ids=[2, 3], top_k=None)
    assert result["content"] == "found"
