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
        mock_model.bind.return_value = mock_model
        mock_model.kwargs = {}
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
