"""Every bundled provider satisfies :class:`LLMProvider` + declares capabilities.

Covers the A2 acceptance bar:

- ``isinstance(p, LLMProvider)`` is True for each bundled provider class
- ``name`` is a non-empty string and ``capabilities`` is a non-empty set
- :meth:`complete_canonical` translates :class:`LLMRequest` → :class:`LLMResponse`
- :meth:`stream_canonical` translates legacy events → :class:`StreamChunk`
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest

from ai_portal.catalog.providers.anthropic_native import AnthropicNativeChatProvider
from ai_portal.catalog.providers.canonical_adapter import (
    request_to_legacy_messages,
    tools_to_legacy,
)
from ai_portal.catalog.providers.events import ProviderStreamEvent
from ai_portal.catalog.providers.gemini_native import GeminiNativeChatProvider
from ai_portal.catalog.providers.langchain import LangChainChatProvider
from ai_portal.catalog.providers.protocol import ChatProvider, LLMProvider
from ai_portal.gateway.types import (
    Capability,
    HealthStatus,
    ImageBlock,
    IterationComplete,
    LLMRequest,
    LLMResponse,
    Message,
    ModelInfo,
    ProviderError,
    StreamChunk,
    TextBlock,
    TextDelta,
    ToolDef,
    ToolResultBlock,
    ToolUseBlock,
    UsageChunk,
)


def _fake_settings() -> SimpleNamespace:
    """Minimal Settings stand-in so providers can be instantiated."""
    return SimpleNamespace(
        anthropic_api_key="fake-anthropic-key",
        gemini_api_key="fake-gemini-key",
        chat_default_api_model="gpt-4o-mini",
        use_native_anthropic=True,
        use_native_gemini=True,
        langfuse_public_key="",
        langfuse_secret_key="",
        langfuse_host="",
    )


PROVIDER_CLASSES = [
    AnthropicNativeChatProvider,
    GeminiNativeChatProvider,
    LangChainChatProvider,
]


# ── name + capabilities + protocol membership ───────────────────────────────


@pytest.mark.parametrize("cls", PROVIDER_CLASSES)
def test_provider_declares_name(cls):
    assert isinstance(cls.name, str)
    assert cls.name, f"{cls.__name__}.name must be non-empty"


@pytest.mark.parametrize("cls", PROVIDER_CLASSES)
def test_provider_declares_capabilities(cls):
    caps = cls.capabilities
    assert isinstance(caps, set), f"{cls.__name__}.capabilities must be a set"
    assert len(caps) > 0, f"{cls.__name__}.capabilities must be non-empty"
    # all entries must be members of the Capability literal
    valid_caps = set(Capability.__args__)  # type: ignore[attr-defined]
    invalid = caps - valid_caps
    assert not invalid, f"{cls.__name__} declares unknown capabilities: {invalid}"


@pytest.mark.parametrize("cls", PROVIDER_CLASSES)
def test_provider_isinstance_llmprovider(cls, monkeypatch):
    """Each bundled provider's instance passes :func:`isinstance` for both protocols."""
    p = cls(_fake_settings())
    assert isinstance(p, LLMProvider), (
        f"{cls.__name__} instance must satisfy LLMProvider runtime-check"
    )
    # legacy contract still satisfied
    assert isinstance(p, ChatProvider), (
        f"{cls.__name__} instance must still satisfy ChatProvider"
    )


# ── canonical complete: translate via legacy hook ───────────────────────────


@pytest.mark.parametrize("cls", PROVIDER_CLASSES)
def test_complete_canonical_translates_to_llm_response(cls, monkeypatch):
    p = cls(_fake_settings())
    # stub the legacy sync .complete() to return a vendor-shaped dict
    monkeypatch.setattr(
        p,
        "complete",
        lambda messages, *, model=None: {
            "choices": [{"message": {"role": "assistant", "content": "hello back"}}]
        },
    )

    req = LLMRequest(
        model="some-model",
        messages=[Message(role="user", content=[TextBlock(text="hi")])],
    )
    import asyncio
    resp = asyncio.run(p.complete_canonical(req))
    assert isinstance(resp, LLMResponse)
    assert resp.provider == cls.name
    assert resp.model_used == "some-model"
    assert resp.content[0].text == "hello back"  # type: ignore[union-attr]


# ── canonical stream: translate legacy events → StreamChunk ─────────────────


@pytest.mark.parametrize("cls", PROVIDER_CLASSES)
def test_stream_canonical_translates_events(cls, monkeypatch):
    p = cls(_fake_settings())

    async def fake_stream(*, messages, model, settings, tools=None):
        yield ProviderStreamEvent.model_validate({"type": "text_delta", "text": "hi"})
        yield ProviderStreamEvent.model_validate({
            "type": "usage",
            "input_tokens": 5,
            "output_tokens": 7,
            "cached_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "reasoning_tokens": 0,
        })
        yield ProviderStreamEvent.model_validate({
            "type": "iteration_complete",
            "stop_reason": "end_turn",
        })

    monkeypatch.setattr(p, "stream", fake_stream)

    req = LLMRequest(
        model="some-model",
        messages=[Message(role="user", content=[TextBlock(text="hi")])],
    )
    import asyncio

    async def collect():
        out = []
        async for chunk in p.stream_canonical(req):
            out.append(chunk)
        return out

    chunks = asyncio.run(collect())
    assert len(chunks) == 3
    assert isinstance(chunks[0].root, TextDelta)
    assert isinstance(chunks[1].root, UsageChunk)
    assert isinstance(chunks[2].root, IterationComplete)
    assert chunks[2].root.stop_reason == "end_turn"


# ── canonical default behaviour: count_tokens / list_models / health / embed ─


@pytest.mark.parametrize("cls", PROVIDER_CLASSES)
def test_count_tokens_default_heuristic(cls):
    p = cls(_fake_settings())
    assert p.count_tokens("", "m") == 0
    assert p.count_tokens("abcdefgh", "m") == 2  # 8 chars // 4


@pytest.mark.parametrize("cls", PROVIDER_CLASSES)
def test_list_models_default_empty(cls):
    import asyncio
    p = cls(_fake_settings())
    out = asyncio.run(p.list_models())
    assert isinstance(out, list)
    assert all(isinstance(m, ModelInfo) for m in out)


@pytest.mark.parametrize("cls", PROVIDER_CLASSES)
def test_health_default(cls):
    import asyncio
    p = cls(_fake_settings())
    hs = asyncio.run(p.health())
    assert isinstance(hs, HealthStatus)
    assert hs.healthy is True


@pytest.mark.parametrize("cls", PROVIDER_CLASSES)
def test_embed_default_raises(cls):
    import asyncio
    p = cls(_fake_settings())
    with pytest.raises(NotImplementedError):
        asyncio.run(p.embed(["x"], "any-model"))


# ── translator helpers ──────────────────────────────────────────────────────


def test_request_to_legacy_messages_basic():
    req = LLMRequest(
        model="m",
        messages=[
            Message(role="system", content=[TextBlock(text="be brief")]),
            Message(role="user", content=[TextBlock(text="ping")]),
        ],
    )
    out = request_to_legacy_messages(req)
    assert out == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "ping"},
    ]


def test_request_to_legacy_messages_tool_use_assistant():
    req = LLMRequest(
        model="m",
        messages=[
            Message(role="user", content=[TextBlock(text="search please")]),
            Message(
                role="assistant",
                content=[
                    TextBlock(text="ok"),
                    ToolUseBlock(id="tu_1", name="search", input={"q": "x"}),
                ],
            ),
            Message(
                role="tool",
                content=[ToolResultBlock(tool_use_id="tu_1", content="found 3 hits")],
            ),
        ],
    )
    out = request_to_legacy_messages(req)
    assert out[1]["role"] == "assistant"
    assert "tool_calls" in out[1]
    assert out[1]["tool_calls"][0]["function"]["name"] == "search"
    assert out[2] == {
        "role": "tool",
        "content": "found 3 hits",
        "tool_call_id": "tu_1",
    }


def test_request_to_legacy_messages_image_block_stringified():
    req = LLMRequest(
        model="m",
        messages=[
            Message(
                role="user",
                content=[
                    TextBlock(text="see "),
                    ImageBlock(url="https://x/y.png"),
                ],
            )
        ],
    )
    out = request_to_legacy_messages(req)
    assert "https://x/y.png" in out[0]["content"]


def test_tools_to_legacy_translates_input_schema():
    req = LLMRequest(
        model="m",
        messages=[],
        tools=[
            ToolDef(
                name="search",
                description="Search the web",
                input_schema={
                    "type": "object",
                    "properties": {"q": {"type": "string"}},
                    "required": ["q"],
                },
            )
        ],
    )
    out = tools_to_legacy(req)
    assert out is not None
    assert out[0]["type"] == "function"
    assert out[0]["function"]["name"] == "search"
    assert out[0]["function"]["parameters"]["required"] == ["q"]


def test_tools_to_legacy_none_when_no_tools():
    req = LLMRequest(model="m", messages=[])
    assert tools_to_legacy(req) is None
