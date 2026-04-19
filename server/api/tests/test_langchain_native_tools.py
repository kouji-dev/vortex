"""Tests for LangChain provider handling of native tool dicts."""
from unittest.mock import MagicMock, patch


def _make_chunk(text=None, tool_call_chunks=None, content=None):
    chunk = MagicMock()
    chunk.text = text or ""
    # content is a list of blocks (Anthropic style) or a string (OpenAI style)
    chunk.content = content if content is not None else (text or "")
    chunk.tool_call_chunks = tool_call_chunks or []
    chunk.additional_kwargs = {}
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


def test_stream_deltas_accumulates_input_json_delta_for_server_tool_use():
    """server_tool_use arrives with input:{} first; query comes via input_json_delta chunks."""
    from ai_portal.catalog.providers.langchain import LangChainChatProvider
    from ai_portal.core.config import Settings

    provider = LangChainChatProvider(Settings())

    # Simulate real Anthropic streaming sequence:
    # 1. content_block_start  → server_tool_use with empty input + id
    # 2. content_block_delta  → input_json_delta with partial JSON
    # 3. content_block_delta  → input_json_delta with remaining JSON
    # 4. text chunk           → text response
    chunk_start = _make_chunk(content=[{
        "type": "server_tool_use",
        "name": "web_search",
        "id": "srvtoolu_xyz",
        "input": {},
    }])
    chunk_delta1 = _make_chunk(content=[{
        "type": "input_json_delta",
        "index": 0,
        "partial_json": '{"query": "EUW',
    }])
    chunk_delta2 = _make_chunk(content=[{
        "type": "input_json_delta",
        "index": 0,
        "partial_json": ' rank 1"}',
    }])
    chunk_text = _make_chunk(text="Faker is rank 1.")

    with patch.object(provider, "_chat_model") as mock_cm:
        mock_model = MagicMock()
        mock_model.bind_tools.return_value = mock_model
        mock_model.stream.return_value = iter([chunk_start, chunk_delta1, chunk_delta2, chunk_text])
        mock_cm.return_value = mock_model

        pieces = list(provider.stream_deltas_with_tools(
            [{"role": "user", "content": "who is rank 1 EUW?"}],
            model="claude-sonnet-4-6",
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
        ))

    server_tool_pieces = [p for p in pieces if p.get("type") == "server_tool_use"]
    assert len(server_tool_pieces) == 1, f"Expected 1 server_tool_use, got {server_tool_pieces}"
    assert server_tool_pieces[0]["name"] == "web_search"
    assert server_tool_pieces[0]["input"].get("query") == "EUW rank 1"

    # server_tool_use must appear before the text delta in the output
    srv_idx = next(i for i, p in enumerate(pieces) if p.get("type") == "server_tool_use")
    text_idx = next(i for i, p in enumerate(pieces) if p.get("type") == "delta")
    assert srv_idx < text_idx, "server_tool_use chip must precede text deltas"


def test_stream_deltas_emits_server_tool_use_for_anthropic_native_search():
    from ai_portal.catalog.providers.langchain import LangChainChatProvider
    from ai_portal.core.config import Settings

    provider = LangChainChatProvider(Settings())

    # Simulate Anthropic streaming: chunk has server_tool_use as a content list block
    chunk_tool = _make_chunk(content=[{
        "type": "server_tool_use",
        "name": "web_search",
        "id": "srvtoolu_abc",
        "input": {"query": "LoL EUW rank 1"},
        "index": 0,
    }])
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


def test_streaming_service_emits_chip_for_server_tool_use():
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

    item_done_events = [
        e for e in events
        if e.get("type") == "item_done" and e.get("item", {}).get("kind") == "web_search"
    ]
    assert len(item_done_events) >= 1
