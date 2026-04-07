"""Chat completions via LangChain (ChatAnthropic / ChatOpenAI)."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from ai_portal.core.config import Settings
from ai_portal.catalog.providers.routing import (
    chat_provider_credential_kwargs,
    is_langchain_anthropic_model,
    normalize_model_id_for_langchain_chat,
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
    ) -> Iterator[dict[str, Any]]:
        mid = self._resolved_model_id(model)
        chat = self._chat_model(mid)
        if tools:
            chat = chat.bind_tools(tools)
        lc_messages = _map_dict_messages_to_lc(messages)

        tc_name: str | None = None
        tc_args_parts: list[str] = []

        for chunk in chat.stream(lc_messages):
            # Accumulate tool-call chunks
            tc_chunks = getattr(chunk, "tool_call_chunks", None)
            if tc_chunks:
                for tcc in tc_chunks:
                    if tcc.get("name"):
                        tc_name = tcc["name"]
                    tc_args_parts.append(tcc.get("args", "") or "")
                continue

            text = _chunk_assistant_text(chunk)
            if text:
                yield {"type": "delta", "text": text}

        if tc_name is not None:
            raw_args = "".join(tc_args_parts)
            yield {
                "type": "tool_call",
                "tool_call": {"name": tc_name, "arguments": raw_args},
            }
