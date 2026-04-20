"""Chat completions via LangChain (ChatAnthropic / ChatOpenAI)."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Iterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from ai_portal.catalog.providers.events import (
    IterationCompleteEvent,
    ProviderErrorEvent,
    ProviderStreamEvent,
    TextDeltaEvent,
    ToolCallRequestEvent,
    UsageEvent,
)

from ai_portal.core.config import Settings
from ai_portal.catalog.providers.routing import (
    chat_provider_credential_kwargs,
    is_langchain_anthropic_model,
    is_langchain_gemini_model,
    normalize_model_id_for_langchain_chat,
    normalize_model_id_for_gemini,
)
from ai_portal.catalog.service import effective_chat_model

logger = logging.getLogger(__name__)


def _map_dict_messages_to_lc(messages: list[dict[str, Any]]) -> list:
    out: list = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "") or ""
        if role == "system":
            out.append(SystemMessage(content=content))
        elif role == "assistant":
            tool_calls = m.get("tool_calls")
            if tool_calls:
                lc_tool_calls = []
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    raw_args = fn.get("arguments", "{}")
                    parsed = raw_args if isinstance(raw_args, dict) else json.loads(raw_args)
                    lc_tool_calls.append(
                        {"name": fn.get("name", ""), "args": parsed, "id": tc.get("id", "")}
                    )
                out.append(AIMessage(content=content, tool_calls=lc_tool_calls))
            else:
                out.append(AIMessage(content=content))
        elif role == "tool":
            out.append(
                ToolMessage(
                    content=content,
                    tool_call_id=m.get("tool_call_id", ""),
                )
            )
        else:
            out.append(HumanMessage(content=content))
    return out


def _message_content_to_str(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)


def _chunk_assistant_text(chunk: Any) -> str:
    text = getattr(chunk, "text", None)
    if isinstance(text, str) and text:
        return text
    return _message_content_to_str(getattr(chunk, "content", None))


def _flush_pending_srv(pending_srv: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Yield accumulated server_tool_use blocks and clear the buffer."""
    for pending in list(pending_srv):
        full_input = pending.get("full_input")
        if full_input:
            accumulated_input: dict = full_input
        else:
            parts = pending.get("parts", [])
            try:
                accumulated_input = json.loads("".join(parts)) if parts else {}
            except Exception:
                accumulated_input = {}
        yield {
            "type": "server_tool_use",
            "name": pending["name"],
            "input": accumulated_input,
            "id": pending["id"],
        }
    pending_srv.clear()


class LangChainChatProvider:
    """Chat via LangChain using Anthropic or OpenAI-compatible endpoints."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        if settings.langfuse_public_key and settings.langfuse_secret_key:
            logger.info(
                "langfuse_configured",
                extra={
                    "langfuse_host": settings.langfuse_host,
                    "hint": "trace hooks can be added here",
                },
            )

    def _resolved_model_id(self, model: str | None) -> str:
        raw = effective_chat_model(self._settings, model)
        return normalize_model_id_for_langchain_chat(raw)

    def _chat_model(self, mid: str):
        from langchain_anthropic import ChatAnthropic  # pylint: disable=import-error
        from langchain_openai import ChatOpenAI  # pylint: disable=import-error

        if is_langchain_anthropic_model(mid):
            kw = chat_provider_credential_kwargs(self._settings, f"anthropic/{mid}")
            return ChatAnthropic(model=mid, api_key=kw["api_key"])
        if is_langchain_gemini_model(mid):
            from langchain_google_genai import ChatGoogleGenerativeAI  # pylint: disable=import-error
            gemini_mid = normalize_model_id_for_gemini(mid)
            kw = chat_provider_credential_kwargs(self._settings, gemini_mid)
            return ChatGoogleGenerativeAI(
                model=gemini_mid,
                google_api_key=kw["api_key"],
                max_retries=0,  # disable SDK-level retries; let the app handle errors immediately
            )
        kw = chat_provider_credential_kwargs(self._settings, mid)
        return ChatOpenAI(
            model=mid,
            api_key=kw["api_key"],
            base_url=kw["api_base"],
        )

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        mid = self._resolved_model_id(model)
        chat = self._chat_model(mid)
        lc_messages = _map_dict_messages_to_lc(messages)
        resp = chat.invoke(lc_messages)
        content = _message_content_to_str(getattr(resp, "content", resp))
        return {"choices": [{"message": {"content": content}}]}

    def complete_structured[T](
        self,
        messages: list[dict[str, str]],
        *,
        schema: type[T],
        model: str | None = None,
    ) -> T:
        mid = self._resolved_model_id(model)
        chat = self._chat_model(mid)
        structured = chat.with_structured_output(schema)
        lc_messages = _map_dict_messages_to_lc(messages)
        return structured.invoke(lc_messages)

    def stream_deltas(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> Iterator[str]:
        mid = self._resolved_model_id(model)
        chat = self._chat_model(mid)
        lc_messages = _map_dict_messages_to_lc(messages)
        for chunk in chat.stream(lc_messages):
            piece = _chunk_assistant_text(chunk)
            if piece:
                yield piece

    def stream_deltas_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        mid = self._resolved_model_id(model)
        chat = self._chat_model(mid)

        if tools:
            if is_langchain_anthropic_model(mid):
                # For Anthropic: bind_tools handles both native (web_search_20260209)
                # and standard function tools — _is_builtin_tool passes native dicts through as-is.
                chat = chat.bind_tools(
                    tools,
                    **{"tool_choice": tool_choice} if tool_choice else {},
                )
            else:
                # Other providers: only pass standard function-typed tools.
                function_tools = [
                    t for t in tools
                    if t.get("type") == "function" or "function" in t
                ]
                if function_tools:
                    chat = chat.bind_tools(
                        function_tools,
                        **{"tool_choice": tool_choice} if tool_choice else {},
                    )

        lc_messages = _map_dict_messages_to_lc(messages)
        tc_name: str | None = None
        tc_args_parts: list[str] = []

        # Buffer server_tool_use blocks whose input arrives via subsequent input_json_delta chunks.
        # langchain-anthropic emits content_block_start with input:{} first, then streams the
        # query via input_json_delta events.  We accumulate before yielding so the chip has a query.
        _pending_srv: list[dict[str, Any]] = []

        for chunk in chat.stream(lc_messages):
            content = getattr(chunk, "content", None)
            ak = getattr(chunk, "additional_kwargs", {}) or {}
            tc_raw = getattr(chunk, "tool_call_chunks", None)
            if content or ak or tc_raw:
                logger.debug(
                    "langchain_chunk type=%s content=%r ak=%r tc=%r",
                    type(chunk).__name__,
                    content,
                    ak,
                    tc_raw,
                )

            # Detect Anthropic server_tool_use blocks and accumulate their inputs.
            # langchain-anthropic puts them in chunk.content as list items; the input
            # arrives via "input_json_delta" blocks in subsequent chunks.
            if isinstance(content, list):
                has_srv_block = False
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    block_type = block.get("type")

                    if block_type == "server_tool_use":
                        has_srv_block = True
                        srv_id = block.get("id", "")
                        srv_name = block.get("name", "")
                        srv_input = block.get("input") or {}
                        if srv_input:
                            # Input already fully provided in this chunk.
                            existing = next((p for p in _pending_srv if p["id"] == srv_id), None)
                            if existing:
                                existing["full_input"] = srv_input
                            else:
                                yield {
                                    "type": "server_tool_use",
                                    "name": srv_name,
                                    "input": srv_input,
                                    "id": srv_id,
                                }
                        elif srv_name or srv_id:
                            # Input not yet available — buffer for accumulation via deltas.
                            if not any(p["id"] == srv_id for p in _pending_srv):
                                _pending_srv.append(
                                    {"id": srv_id, "name": srv_name, "parts": [], "full_input": None}
                                )
                        continue

                    elif block_type == "input_json_delta":
                        # Partial JSON input for the most recent pending server_tool_use block.
                        partial = block.get("partial_json", "") or ""
                        if partial and _pending_srv:
                            _pending_srv[-1]["parts"].append(partial)
                        continue

                if has_srv_block:
                    continue

            # Standard client-side tool call chunks
            tc_chunks = getattr(chunk, "tool_call_chunks", None)
            if tc_chunks:
                for tcc in tc_chunks:
                    if tcc.get("name"):
                        tc_name = tcc["name"]
                    tc_args_parts.append(tcc.get("args", "") or "")
                continue

            text = _chunk_assistant_text(chunk)
            if text:
                # Flush any pending server_tool_use blocks before emitting text (preserves order).
                if _pending_srv:
                    yield from _flush_pending_srv(_pending_srv)
                yield {"type": "delta", "text": text}

        # Stream ended — flush any remaining pending server_tool_use blocks.
        if _pending_srv:
            yield from _flush_pending_srv(_pending_srv)

        if tc_name is not None:
            raw_args = "".join(tc_args_parts)
            yield {
                "type": "tool_call",
                "tool_call": {"name": tc_name, "arguments": raw_args},
            }

    # ── Typed async stream ───────────────────────────────────────────────────

    async def stream(
        self,
        *,
        messages: list[dict],
        model: str,
        settings: dict,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[ProviderStreamEvent]:
        """Async typed stream yielding ProviderStreamEvent.

        Iterates over the LangChain chat model's .stream() output, translating
        AIMessageChunk objects into typed ProviderStreamEvent instances.

        # NOTE: This stream() path does not support server_tool_use events (Anthropic web_search,
        # Gemini grounding). For server-tool support, use the native provider adapters directly.
        # Phase 6 will make this explicit via routing.
        """
        try:
            mid = self._resolved_model_id(model)
            chat = self._chat_model(mid)
            lc_messages = _map_dict_messages_to_lc(messages)

            stop_reason = "end_turn"

            for chunk in chat.stream(lc_messages):
                # Text content
                text = _chunk_assistant_text(chunk)
                if text:
                    yield ProviderStreamEvent.model_validate(
                        {"type": "text_delta", "text": text}
                    )

                # Tool calls (fully resolved, from .tool_calls attribute)
                tool_calls = getattr(chunk, "tool_calls", None) or []
                for tc in tool_calls:
                    args = tc.get("args", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    yield ProviderStreamEvent.model_validate({
                        "type": "tool_call_request",
                        "call_id": tc.get("id", ""),
                        "tool_name": tc.get("name", ""),
                        "arguments": args,
                    })
                    stop_reason = "tool_use"

                # Usage metadata
                usage_meta = getattr(chunk, "usage_metadata", None)
                if usage_meta and isinstance(usage_meta, dict):
                    yield ProviderStreamEvent.model_validate({
                        "type": "usage",
                        "input_tokens": usage_meta.get("input_tokens", 0) or 0,
                        "output_tokens": usage_meta.get("output_tokens", 0) or 0,
                        "cached_input_tokens": usage_meta.get("cached_tokens", 0) or 0,
                        "cache_creation_input_tokens": 0,
                        "reasoning_tokens": 0,
                    })

            # Synthesize iteration_complete after stream ends
            yield ProviderStreamEvent.model_validate({
                "type": "iteration_complete",
                "stop_reason": stop_reason,
            })

        except Exception as exc:
            logger.error("langchain.stream: error %s", exc)
            yield ProviderStreamEvent.model_validate({
                "type": "provider_error",
                "code": type(exc).__name__,
                "message": str(exc),
            })
