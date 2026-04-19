"""Native Anthropic chat provider — uses the Anthropic SDK directly.

Benefits over LangChain path:
  - Prompt caching (``cache_control: ephemeral``) on stable segment → 60–80%
    cost reduction on repeated long system prompts.
  - Extended thinking (``thinking`` param) surfaced as ``{"type": "thinking"}``
    events; stored in ``ChatMessage.extra.thinking``.
  - Native ``web_search_20260209`` server tool without LangChain shim overhead.
  - Clean ``usage`` event with cache token counts for cost metering.
  - ``citation`` events when web search results include source references.

Usage:
  provider = AnthropicNativeChatProvider(settings)
  for piece in provider.stream_deltas_with_tools(messages, model=model_id, tools=tools):
      ...  # same event shape as LangChainChatProvider
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

import anthropic

from ai_portal.core.config import Settings
from ai_portal.catalog.providers.base import BaseLlmProvider
from ai_portal.catalog.providers.routing import (
    normalize_model_id_for_langchain_chat,
    remap_deprecated_chat_model,
    _is_anthropic_style_model,
)

logger = logging.getLogger(__name__)

_DEFAULT_MAX_TOKENS = 16_000
_THINKING_BUDGET_TOKENS = 8_000


def _normalize_model(model: str) -> str:
    m = remap_deprecated_chat_model((model or "").strip())
    # Strip catalog prefix (anthropic-claude-haiku-4-5 → claude-haiku-4-5)
    return normalize_model_id_for_langchain_chat(m)


def _is_thinking_model(model: str) -> bool:
    m = _normalize_model(model).lower()
    return "claude-3-7" in m or "claude-opus-4" in m or "claude-sonnet-4" in m


def _to_anthropic_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert streaming_service message dicts to Anthropic SDK format.

    Handles user/assistant/tool roles. System messages are stripped (passed
    separately via the ``system`` param).
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content") or ""

        if role == "system":
            continue

        if role == "tool":
            # Tool result — must follow as user turn
            out.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": m.get("tool_call_id", ""),
                    "content": str(content),
                }],
            })
            continue

        if role == "assistant":
            tool_calls = m.get("tool_calls")
            if tool_calls:
                blocks: list[dict] = []
                if content:
                    blocks.append({"type": "text", "text": str(content)})
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    raw_args = fn.get("arguments", "{}")
                    try:
                        inp = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except Exception:
                        inp = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", "tool_0"),
                        "name": fn.get("name", ""),
                        "input": inp,
                    })
                out.append({"role": "assistant", "content": blocks})
            else:
                out.append({"role": "assistant", "content": str(content)})
            continue

        out.append({"role": "user", "content": str(content)})

    # Anthropic requires alternating user/assistant; merge consecutive same-role turns.
    merged: list[dict[str, Any]] = []
    for msg in out:
        if merged and merged[-1]["role"] == msg["role"] == "user":
            prev_content = merged[-1]["content"]
            new_content = msg["content"]
            if isinstance(prev_content, str) and isinstance(new_content, str):
                merged[-1]["content"] = prev_content + "\n" + new_content
            elif isinstance(prev_content, list) and isinstance(new_content, str):
                prev_content.append({"type": "text", "text": new_content})
            elif isinstance(prev_content, str) and isinstance(new_content, list):
                merged[-1]["content"] = [{"type": "text", "text": prev_content}] + new_content
            elif isinstance(prev_content, list) and isinstance(new_content, list):
                prev_content.extend(new_content)
        else:
            merged.append(msg)

    return merged


def _build_system_blocks(system_text: str) -> list[dict[str, Any]] | str:
    """Add cache_control to the system prompt block for prompt caching."""
    if not system_text:
        return ""
    return [
        {
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def _convert_tool(tool: dict[str, Any]) -> dict[str, Any] | None:
    """Convert streaming_service tool dict to Anthropic tool format."""
    # Native server tools pass through as-is (already Anthropic format).
    if tool.get("type") in ("web_search_20260209", "web_search_20250305"):
        return tool

    fn = tool.get("function")
    if not fn:
        return None

    props = fn.get("parameters", {}).get("properties", {})
    required = fn.get("parameters", {}).get("required", [])
    return {
        "type": "custom",
        "name": fn.get("name", ""),
        "description": fn.get("description", ""),
        "input_schema": {
            "type": "object",
            "properties": props,
            "required": required,
        },
    }


class AnthropicNativeChatProvider(BaseLlmProvider):
    """Streaming chat provider using the Anthropic SDK directly."""

    _normalize_model_id = staticmethod(
        lambda m: normalize_model_id_for_langchain_chat(remap_deprecated_chat_model(m))
    )

    def __init__(self, settings: Settings) -> None:
        key = settings.anthropic_api_key.strip()
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set — required for Anthropic native provider"
            )
        super().__init__(settings)
        self._client = anthropic.Anthropic(api_key=key)

    def complete(self, messages: list[dict[str, str]], *, model: str | None = None) -> dict[str, Any]:
        mid = self._resolved_model(model)
        system_text = self._extract_system_text(messages)
        ant_messages = _to_anthropic_messages(messages)
        resp = self._client.messages.create(
            model=mid,
            max_tokens=_DEFAULT_MAX_TOKENS,
            messages=ant_messages,
            system=_build_system_blocks(system_text),
        )
        content = "".join(b.text for b in resp.content if hasattr(b, "text"))
        return {"choices": [{"message": {"role": "assistant", "content": content}}]}

    def stream_deltas_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        mid = self._resolved_model(model)
        system_text = self._extract_system_text(messages)
        ant_messages = _to_anthropic_messages(messages)

        # Build tool list for Anthropic.
        ant_tools: list[dict[str, Any]] = []
        has_web_search = False
        if tools:
            for t in tools:
                converted = _convert_tool(t)
                if converted is None:
                    continue
                if converted.get("type") in ("web_search_20260209", "web_search_20250305"):
                    has_web_search = True
                    # Anthropic native web search: country hint.
                    converted = {
                        "type": "web_search_20260209",
                        "name": "web_search",
                        "max_uses": 5,
                    }
                ant_tools.append(converted)

        kwargs: dict[str, Any] = {
            "model": mid,
            "max_tokens": _DEFAULT_MAX_TOKENS,
            "messages": ant_messages,
        }

        sys_blocks = _build_system_blocks(system_text)
        if sys_blocks:
            kwargs["system"] = sys_blocks

        if ant_tools:
            kwargs["tools"] = ant_tools
            # Add cache_control to tool definitions for prompt caching.
            if ant_tools:
                ant_tools[-1] = {**ant_tools[-1], "cache_control": {"type": "ephemeral"}}

        if tool_choice and not has_web_search:
            if tool_choice == "auto":
                kwargs["tool_choice"] = {"type": "auto"}
            elif tool_choice == "none":
                kwargs["tool_choice"] = {"type": "none"}
            elif tool_choice:
                kwargs["tool_choice"] = {"type": "tool", "name": tool_choice}

        # Extended thinking for supported models.
        if _is_thinking_model(mid):
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": _THINKING_BUDGET_TOKENS}
            # Thinking is incompatible with temperature != 1.
        else:
            kwargs["thinking"] = {"type": "disabled"}

        logger.debug(
            "anthropic_native: model=%s tools=%d messages=%d thinking=%s",
            mid,
            len(ant_tools),
            len(ant_messages),
            kwargs.get("thinking", {}).get("type"),
        )

        current_block_type: str | None = None
        pending_tool_name: str | None = None
        pending_tool_id: str | None = None
        pending_tool_args_parts: list[str] = []

        # Usage accumulators.
        input_tokens = 0
        output_tokens = 0
        cache_creation_tokens = 0
        cache_read_tokens = 0

        try:
            with self._client.messages.stream(**kwargs) as stream:
                for event in stream:
                    event_type = type(event).__name__

                    if event_type == "RawMessageStartEvent":
                        usage = event.message.usage
                        input_tokens += getattr(usage, "input_tokens", 0) or 0
                        cache_creation_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
                        cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0

                    elif event_type == "RawContentBlockStartEvent":
                        block = event.content_block
                        btype = getattr(block, "type", None)
                        current_block_type = btype

                        if btype == "tool_use":
                            pending_tool_name = getattr(block, "name", "")
                            pending_tool_id = getattr(block, "id", "")
                            pending_tool_args_parts = []

                        elif btype == "server_tool_use":
                            srv_name = getattr(block, "name", "web_search")
                            srv_id = getattr(block, "id", "")
                            yield {
                                "type": "server_tool_use",
                                "name": srv_name,
                                "input": {},
                                "id": srv_id,
                            }

                    elif event_type == "RawContentBlockDeltaEvent":
                        delta = event.delta
                        dtype = getattr(delta, "type", None)

                        if dtype == "text_delta":
                            text = getattr(delta, "text", "") or ""
                            if text:
                                yield {"type": "delta", "text": text}

                        elif dtype == "thinking_delta":
                            thinking = getattr(delta, "thinking", "") or ""
                            if thinking:
                                yield {"type": "thinking", "text": thinking}

                        elif dtype == "input_json_delta" and current_block_type == "tool_use":
                            partial = getattr(delta, "partial_json", "") or ""
                            pending_tool_args_parts.append(partial)

                        elif dtype == "citations_delta":
                            # Web search citation.
                            citations = getattr(delta, "citations", []) or []
                            for cit in citations:
                                url = getattr(cit, "url", None) or getattr(cit, "uri", None)
                                title = getattr(cit, "title", None)
                                snippet = getattr(cit, "cited_text", None)
                                if url:
                                    yield {
                                        "type": "citation",
                                        "url": url,
                                        "title": title,
                                        "snippet": snippet,
                                    }

                    elif event_type == "RawContentBlockStopEvent":
                        if current_block_type == "tool_use" and pending_tool_name:
                            raw_args = "".join(pending_tool_args_parts)
                            yield {
                                "type": "tool_call",
                                "tool_call": {
                                    "name": pending_tool_name,
                                    "arguments": raw_args,
                                    "id": pending_tool_id,
                                },
                            }
                            pending_tool_name = None
                            pending_tool_id = None
                            pending_tool_args_parts = []
                        current_block_type = None

                    elif event_type == "RawMessageDeltaEvent":
                        usage = getattr(event, "usage", None)
                        if usage:
                            output_tokens += getattr(usage, "output_tokens", 0) or 0

                    elif event_type == "RawMessageStopEvent":
                        pass

        except anthropic.APIStatusError as exc:
            logger.error("anthropic_native: APIStatusError %s", exc)
            raise ValueError(str(exc)) from exc

        # Emit aggregated usage once stream is done.
        yield {
            "type": "usage",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_input_tokens": cache_read_tokens,
            "cache_creation_input_tokens": cache_creation_tokens,
            "reasoning_tokens": None,
        }
