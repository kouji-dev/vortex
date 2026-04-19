"""Native Gemini provider — protocol compliance tests (mocked SDK)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_settings() -> MagicMock:
    s = MagicMock()
    s.gemini_api_key = "ggl-test"
    s.chat_default_api_model = "gemini-2.0-flash"
    return s


def _provider():
    from ai_portal.catalog.providers.gemini_native import GeminiNativeChatProvider
    with patch("google.genai.Client"):
        return GeminiNativeChatProvider(_make_settings())


def _make_chunk(text: str = "", function_calls=None, candidates_token_count: int = 5, prompt_token_count: int = 20):
    chunk = MagicMock()
    if text:
        part = MagicMock()
        part.text = text
        part.function_call = None
        candidate = MagicMock()
        candidate.content.parts = [part]
        chunk.candidates = [candidate]
    else:
        chunk.candidates = []

    if function_calls:
        parts = []
        for fc in function_calls:
            p = MagicMock()
            p.text = None
            p.function_call = fc
            parts.append(p)
        cand = MagicMock()
        cand.content.parts = parts
        chunk.candidates = [cand]

    chunk.usage_metadata = MagicMock()
    chunk.usage_metadata.prompt_token_count = prompt_token_count
    chunk.usage_metadata.candidates_token_count = candidates_token_count
    chunk.usage_metadata.cached_content_token_count = 0
    chunk.usage_metadata.thoughts_token_count = 0
    return chunk


def test_stream_emits_delta_events():
    provider = _provider()
    chunks = [_make_chunk("Hello"), _make_chunk(" world")]

    with patch.object(provider._client.models, "generate_content_stream", return_value=iter(chunks)):
        pieces = list(provider.stream_deltas_with_tools(
            [{"role": "user", "content": "hi"}],
            model="gemini-2.0-flash",
        ))

    delta_pieces = [p for p in pieces if p.get("type") == "delta"]
    combined = "".join(p["text"] for p in delta_pieces)
    assert "Hello" in combined or "world" in combined


def test_stream_emits_usage_event():
    provider = _provider()
    chunks = [_make_chunk("ok", prompt_token_count=50, candidates_token_count=10)]

    with patch.object(provider._client.models, "generate_content_stream", return_value=iter(chunks)):
        pieces = list(provider.stream_deltas_with_tools(
            [{"role": "user", "content": "hi"}],
            model="gemini-2.0-flash",
        ))

    usage_pieces = [p for p in pieces if p.get("type") == "usage"]
    assert len(usage_pieces) == 1
    u = usage_pieces[0]
    assert u["input_tokens"] == 50
    assert u["output_tokens"] == 10


def test_stream_emits_tool_call():
    provider = _provider()

    fc = MagicMock()
    fc.name = "fetch_webpage"
    fc.args = {"url": "https://example.com"}
    fc.id = "fc-1"
    chunks = [_make_chunk(function_calls=[fc])]

    with patch.object(provider._client.models, "generate_content_stream", return_value=iter(chunks)):
        pieces = list(provider.stream_deltas_with_tools(
            [{"role": "user", "content": "fetch"}],
            model="gemini-2.0-flash",
            tools=[{"type": "function", "function": {"name": "fetch_webpage", "description": "fetch", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}}],
        ))

    tool_pieces = [p for p in pieces if p.get("type") == "tool_call"]
    assert len(tool_pieces) == 1
    assert tool_pieces[0]["tool_call"]["name"] == "fetch_webpage"


def test_no_api_key_raises():
    import pytest
    from ai_portal.catalog.providers.gemini_native import GeminiNativeChatProvider
    s = MagicMock()
    s.gemini_api_key = ""
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        GeminiNativeChatProvider(s)
