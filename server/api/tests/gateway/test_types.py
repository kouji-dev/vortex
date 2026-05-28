"""Round-trip + construction tests for gateway canonical types."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_portal.gateway.types import (
    CacheHint,
    Citation,
    ContentBlock,
    Embeddings,
    HealthStatus,
    ImageBlock,
    IterationComplete,
    LLMRequest,
    LLMResponse,
    Message,
    ModelInfo,
    ProviderError,
    ResponseFormat,
    ServerToolUse,
    StreamChunk,
    TextBlock,
    TextDelta,
    ThinkingConfig,
    ThinkingDelta,
    ToolCall,
    ToolCallRequest,
    ToolChoice,
    ToolDef,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
    UsageChunk,
)


# ── content blocks ──────────────────────────────────────────────────────────


def test_text_block_round_trip():
    block = TextBlock(text="hello")
    payload = block.model_dump()
    assert payload["type"] == "text"
    assert TextBlock.model_validate(payload) == block


def test_text_block_with_cache_hint():
    block = TextBlock(text="long system prompt", cache_control=CacheHint(ttl="1h"))
    assert block.cache_control is not None
    assert block.cache_control.ttl == "1h"
    again = TextBlock.model_validate(block.model_dump())
    assert again.cache_control.ttl == "1h"


def test_image_block_url_form():
    block = ImageBlock(url="https://example.com/x.png")
    assert block.url == "https://example.com/x.png"
    assert ImageBlock.model_validate(block.model_dump()) == block


def test_image_block_base64_form():
    block = ImageBlock(data_base64="ABCD", media_type="image/jpeg")
    assert block.data_base64 == "ABCD"
    assert block.media_type == "image/jpeg"


def test_tool_use_block():
    block = ToolUseBlock(id="tu_1", name="search", input={"q": "x"})
    again = ToolUseBlock.model_validate(block.model_dump())
    assert again.input == {"q": "x"}


def test_tool_result_block():
    block = ToolResultBlock(tool_use_id="tu_1", content="result")
    assert ToolResultBlock.model_validate(block.model_dump()) == block


def test_content_block_discriminated_dispatch():
    cb = ContentBlock.model_validate({"type": "text", "text": "hi"})
    assert isinstance(cb.root, TextBlock)
    assert cb.kind == "text"

    cb2 = ContentBlock.model_validate(
        {"type": "tool_use", "id": "x", "name": "f", "input": {}}
    )
    assert isinstance(cb2.root, ToolUseBlock)


def test_content_block_unknown_type_rejected():
    with pytest.raises(ValidationError):
        ContentBlock.model_validate({"type": "video", "url": "y"})


# ── messages ────────────────────────────────────────────────────────────────


def test_message_with_mixed_content():
    msg = Message(
        role="user",
        content=[
            TextBlock(text="describe this"),
            ImageBlock(url="https://x/y.png"),
        ],
    )
    payload = msg.model_dump()
    assert payload["role"] == "user"
    assert payload["content"][0]["type"] == "text"
    assert payload["content"][1]["type"] == "image"
    again = Message.model_validate(payload)
    assert len(again.content) == 2


# ── tools ───────────────────────────────────────────────────────────────────


def test_tool_def_round_trip():
    t = ToolDef(
        name="search",
        description="Search the web",
        input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
    )
    assert ToolDef.model_validate(t.model_dump()) == t


def test_tool_choice_modes():
    assert ToolChoice().mode == "auto"
    assert ToolChoice(mode="none").mode == "none"
    assert ToolChoice(mode="tool", tool_name="search").tool_name == "search"


def test_tool_choice_invalid_mode():
    with pytest.raises(ValidationError):
        ToolChoice(mode="something")  # type: ignore[arg-type]


def test_tool_call_round_trip():
    tc = ToolCall(id="c1", name="search", arguments={"q": "x"})
    assert ToolCall.model_validate(tc.model_dump()) == tc


# ── response format / cache / thinking ──────────────────────────────────────


def test_response_format_text_default():
    rf = ResponseFormat()
    assert rf.kind == "text"


def test_response_format_json_schema():
    rf = ResponseFormat(
        kind="json_schema",
        schema_name="Person",
        json_schema={"type": "object"},
        strict=True,
    )
    assert ResponseFormat.model_validate(rf.model_dump()) == rf


def test_cache_hint_ttl_constrained():
    assert CacheHint(ttl="5m").ttl == "5m"
    with pytest.raises(ValidationError):
        CacheHint(ttl="2h")  # type: ignore[arg-type]


def test_thinking_config():
    cfg = ThinkingConfig(enabled=True, budget_tokens=4096)
    assert ThinkingConfig.model_validate(cfg.model_dump()) == cfg


# ── llm request / response ──────────────────────────────────────────────────


def test_llm_request_minimum():
    req = LLMRequest(
        model="claude-sonnet-4-6",
        messages=[Message(role="user", content=[TextBlock(text="hi")])],
    )
    payload = req.model_dump()
    assert payload["model"] == "claude-sonnet-4-6"
    again = LLMRequest.model_validate(payload)
    assert again == req


def test_llm_request_full():
    req = LLMRequest(
        model="smart",
        messages=[
            Message(role="system", content=[TextBlock(text="You are caveman.")]),
            Message(role="user", content=[TextBlock(text="hi")]),
        ],
        tools=[ToolDef(name="search")],
        tool_choice=ToolChoice(mode="auto"),
        response_format=ResponseFormat(kind="json_object"),
        stream=True,
        max_tokens=4096,
        temperature=0.2,
        top_p=0.9,
        stop=["\n\n"],
        metadata={"anthropic-beta": "prompt-caching-2024-07-31"},
        cache_hints=[CacheHint(ttl="5m")],
        thinking=ThinkingConfig(enabled=True, budget_tokens=2048),
        user="user_42",
    )
    again = LLMRequest.model_validate(req.model_dump())
    assert again == req


def test_llm_request_rejects_extra_fields():
    with pytest.raises(ValidationError):
        LLMRequest.model_validate(
            {
                "model": "x",
                "messages": [],
                "made_up_field": "boom",
            }
        )


def test_usage_round_trip():
    u = Usage(input_tokens=10, output_tokens=20, cache_read_tokens=5, total_tokens=35)
    assert Usage.model_validate(u.model_dump()) == u


def test_llm_response_round_trip():
    resp = LLMResponse(
        id="resp_1",
        model_used="claude-sonnet-4-6",
        provider="anthropic",
        content=[TextBlock(text="hello back")],
        tool_calls=[ToolCall(id="c", name="search", arguments={"q": "x"})],
        usage=Usage(input_tokens=10, output_tokens=20),
        stop_reason="end_turn",
        raw={"native": "passthrough"},
    )
    again = LLMResponse.model_validate(resp.model_dump())
    assert again == resp


def test_llm_response_default_stop_reason():
    resp = LLMResponse(id="x", model_used="m", provider="p")
    assert resp.stop_reason == "end_turn"


# ── stream chunks ───────────────────────────────────────────────────────────


def test_stream_chunk_text_delta():
    chunk = StreamChunk.model_validate({"type": "text_delta", "text": "hi"})
    assert isinstance(chunk.root, TextDelta)
    assert chunk.kind == "text_delta"


def test_stream_chunk_thinking_delta():
    chunk = StreamChunk.model_validate({"type": "thinking_delta", "text": "hmm"})
    assert isinstance(chunk.root, ThinkingDelta)


def test_stream_chunk_tool_call_request():
    chunk = StreamChunk.model_validate(
        {
            "type": "tool_call_request",
            "call_id": "c1",
            "tool_name": "search",
            "arguments": {"q": "x"},
        }
    )
    assert isinstance(chunk.root, ToolCallRequest)


def test_stream_chunk_server_tool_use():
    chunk = StreamChunk.model_validate(
        {"type": "server_tool_use", "tool_name": "web_search", "input": {"q": "x"}}
    )
    assert isinstance(chunk.root, ServerToolUse)


def test_stream_chunk_citation():
    chunk = StreamChunk.model_validate(
        {"type": "citation", "url": "https://x", "title": "X", "snippet": "..."}
    )
    assert isinstance(chunk.root, Citation)


def test_stream_chunk_usage():
    chunk = StreamChunk.model_validate(
        {
            "type": "usage",
            "input_tokens": 10,
            "output_tokens": 20,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "reasoning_tokens": 0,
        }
    )
    assert isinstance(chunk.root, UsageChunk)


def test_stream_chunk_iteration_complete():
    chunk = StreamChunk.model_validate(
        {"type": "iteration_complete", "stop_reason": "end_turn"}
    )
    assert isinstance(chunk.root, IterationComplete)


def test_stream_chunk_provider_error():
    chunk = StreamChunk.model_validate(
        {"type": "provider_error", "code": "rate_limited", "message": "slow down"}
    )
    assert isinstance(chunk.root, ProviderError)


def test_stream_chunk_unknown_rejected():
    with pytest.raises(ValidationError):
        StreamChunk.model_validate({"type": "made_up"})


# ── model info + health + embeddings ────────────────────────────────────────


def test_model_info_round_trip():
    mi = ModelInfo(
        id="claude-sonnet-4-6",
        provider="anthropic",
        display_name="Claude Sonnet 4.6",
        capabilities=["chat", "streaming", "tools", "vision", "thinking", "cache"],
        context_window=200_000,
        max_output_tokens=8192,
        price_input_per_1k_cents=0.3,
        price_output_per_1k_cents=1.5,
        price_cache_read_per_1k_cents=0.03,
    )
    assert ModelInfo.model_validate(mi.model_dump()) == mi


def test_health_status():
    hs = HealthStatus(healthy=True, latency_ms=42.0, detail="ok")
    assert HealthStatus.model_validate(hs.model_dump()) == hs


def test_embeddings_round_trip():
    e = Embeddings(
        model="text-embedding-3-small",
        provider="openai",
        vectors=[[0.1, 0.2], [0.3, 0.4]],
        usage=Usage(input_tokens=10, total_tokens=10),
    )
    again = Embeddings.model_validate(e.model_dump())
    assert again == e
