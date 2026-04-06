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
    tool_call_events = [e for e in events if e.get("type") == "item_start" and e.get("item", {}).get("kind") == "tool_call"]
    assert len(tool_call_events) >= 1
    assert tool_call_events[0]["item"]["tool"] == "web_search"


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
    tool_call_events = [e for e in events if e.get("type") == "item_start" and e.get("item", {}).get("kind") == "tool_call"]
    assert any(e["item"]["tool"] == "query_structured_data" for e in tool_call_events)


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


@requires_postgres
def test_item_start_done_protocol():
    """Verify item_start/item_done SSE events are emitted and old tool_call event is gone."""
    r = client.post(
        "/api/chat/conversations",
        headers=AUTH,
        json={"settings": {"capabilities": {"web_search": True}}},
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    call_count = 0

    def fake_stream(messages, model=None, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            yield {"type": "tool_call", "tool_call": {"name": "web_search", "arguments": '{"query": "test query"}'}}
        else:
            yield {"type": "delta", "text": "Here is the answer."}

    with patch("ai_portal.api.conversations.llm_svc.chat_completions_stream_with_tools", side_effect=fake_stream), \
         patch("ai_portal.tools.registry.DuckDuckGoProvider") as MockDDG:
        instance = MagicMock()
        from ai_portal.tools.search.base import SearchResult
        instance.search.return_value = [
            SearchResult(title="Test", url="https://example.com", snippet="Test result")
        ]
        MockDDG.return_value = instance

        resp = client.post(
            f"/api/chat/conversations/{cid}/messages/stream",
            headers=AUTH,
            json={"content": "test question"},
        )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)

    thinking_starts = [e for e in events if e.get("type") == "item_start" and e.get("item", {}).get("kind") == "thinking"]
    assert len(thinking_starts) >= 1

    tool_starts = [e for e in events if e.get("type") == "item_start" and e.get("item", {}).get("kind") == "tool_call"]
    assert len(tool_starts) >= 1
    tool_start = tool_starts[0]
    assert tool_start["item"]["tool"] == "web_search"
    assert "params" in tool_start["item"]
    assert isinstance(tool_start["item"]["params"], dict)

    tool_dones = [e for e in events if e.get("type") == "item_done" and e.get("item", {}).get("kind") == "tool_call"]
    assert len(tool_dones) >= 1
    assert tool_dones[0]["item"]["status"] == "done"

    thinking_dones = [e for e in events if e.get("type") == "item_done" and e.get("item", {}).get("kind") == "thinking"]
    assert len(thinking_dones) >= 1

    old_tool_events = [e for e in events if e.get("type") == "tool_call"]
    assert len(old_tool_events) == 0
