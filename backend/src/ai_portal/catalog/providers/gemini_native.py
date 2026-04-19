"""Native Google Gemini chat provider — uses the google-genai SDK directly.

Benefits over LangChain path:
  - Google Search grounding (native citations, no tool-loop overhead).
  - ``url_context`` tool — Gemini fetches pages inline with its reasoning.
  - Clean ``usage_metadata`` for cost metering (prompt + candidate + cached tokens).
  - ``thinking_config`` for extended thinking on supported models.
  - Eliminates ``gemini_quirks.py`` tool_choice workarounds (native client
    handles tool_choice correctly).

Routing: active when ``use_native_gemini=True`` (default) and model is Gemini.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

import google.genai as genai
import google.genai.types as gtypes

from ai_portal.core.config import Settings
from ai_portal.catalog.providers.base import BaseLlmProvider
from ai_portal.catalog.providers.routing import (
    normalize_model_id_for_gemini,
    remap_deprecated_chat_model,
    _is_gemini_model,
)

logger = logging.getLogger(__name__)

_DEFAULT_MAX_OUTPUT_TOKENS = 16_000
_THINKING_BUDGET_TOKENS = 8_000


def _normalize_model(model: str) -> str:
    m = remap_deprecated_chat_model((model or "").strip())
    return normalize_model_id_for_gemini(m)


def _is_thinking_model(model: str) -> bool:
    m = _normalize_model(model).lower()
    return "flash-thinking" in m or "2.0-flash-thinking" in m or "2.5-pro" in m


def _to_gemini_contents(messages: list[dict[str, Any]]) -> list[gtypes.Content]:
    """Convert streaming_service message dicts to Gemini Content objects.

    System messages are passed separately via config.system_instruction.
    """
    out: list[gtypes.Content] = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content") or ""

        if role == "system":
            continue

        if role == "tool":
            # Tool result — Gemini expects a function response part.
            out.append(
                gtypes.Content(
                    role="user",
                    parts=[
                        gtypes.Part(
                            function_response=gtypes.FunctionResponse(
                                id=m.get("tool_call_id", ""),
                                name=m.get("name", "tool"),
                                response={"result": str(content)},
                            )
                        )
                    ],
                )
            )
            continue

        if role == "assistant":
            tool_calls = m.get("tool_calls")
            if tool_calls:
                parts: list[gtypes.Part] = []
                if content:
                    parts.append(gtypes.Part(text=str(content)))
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    raw_args = fn.get("arguments", "{}")
                    try:
                        inp = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except Exception:
                        inp = {}
                    parts.append(
                        gtypes.Part(
                            function_call=gtypes.FunctionCall(
                                id=tc.get("id", ""),
                                name=fn.get("name", ""),
                                args=inp,
                            )
                        )
                    )
                out.append(gtypes.Content(role="model", parts=parts))
            else:
                out.append(gtypes.Content(role="model", parts=[gtypes.Part(text=str(content))]))
            continue

        out.append(gtypes.Content(role="user", parts=[gtypes.Part(text=str(content))]))

    # Gemini requires contents to start with a user turn. If empty or starts with
    # model, prepend a minimal user turn.
    if not out or out[0].role == "model":
        out.insert(0, gtypes.Content(role="user", parts=[gtypes.Part(text=".")]))

    return out


def _build_tools(
    tools: list[dict[str, Any]] | None,
    use_grounding: bool,
    use_url_context: bool,
) -> list[gtypes.Tool] | None:
    """Build Gemini Tool objects from streaming_service tool dicts."""
    tool_list: list[gtypes.Tool] = []

    if use_grounding:
        tool_list.append(gtypes.Tool(google_search=gtypes.GoogleSearch()))

    if use_url_context:
        tool_list.append(gtypes.Tool(url_context=gtypes.UrlContext()))

    if tools:
        fn_decls: list[gtypes.FunctionDeclaration] = []
        for t in tools:
            fn = t.get("function")
            if not fn:
                continue
            params = fn.get("parameters", {})
            fn_decls.append(
                gtypes.FunctionDeclaration(
                    name=fn.get("name", ""),
                    description=fn.get("description", ""),
                    parameters=params if params.get("properties") else None,
                )
            )
        if fn_decls:
            tool_list.append(gtypes.Tool(function_declarations=fn_decls))

    return tool_list or None


class GeminiNativeChatProvider(BaseLlmProvider):
    """Streaming chat provider using the Google Gemini SDK directly."""

    _normalize_model_id = staticmethod(
        lambda m: normalize_model_id_for_gemini(remap_deprecated_chat_model(m))
    )

    def __init__(self, settings: Settings) -> None:
        key = settings.gemini_api_key.strip()
        if not key:
            raise ValueError(
                "GEMINI_API_KEY is not set — required for Gemini native provider"
            )
        super().__init__(settings)
        self._client = genai.Client(api_key=key)

    def complete(self, messages: list[dict[str, str]], *, model: str | None = None) -> dict[str, Any]:
        mid = self._resolved_model(model)
        system_text = self._extract_system_text(messages)
        contents = _to_gemini_contents(messages)
        cfg = gtypes.GenerateContentConfig(
            system_instruction=system_text if system_text else None,
            max_output_tokens=_DEFAULT_MAX_OUTPUT_TOKENS,
        )
        resp = self._client.models.generate_content(model=mid, contents=contents, config=cfg)
        text = resp.text or ""
        return {"choices": [{"message": {"role": "assistant", "content": text}}]}

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
        contents = _to_gemini_contents(messages)

        # Enable grounding when the conversation uses research or has no KBs.
        # Never combine grounding with function tools (can produce conflicting citations).
        has_function_tools = bool(tools and any(t.get("function") for t in (tools or [])))
        use_grounding = not has_function_tools and bool(tools and any(
            t.get("type") in ("web_search", "web_search_20260209") for t in (tools or [])
        ))
        # url_context: enable when fetch_webpage tool is requested.
        use_url_context = bool(tools and any(
            t.get("function", {}).get("name") == "fetch_webpage" for t in (tools or [])
        ))

        gemini_tools = _build_tools(
            # Only pass function tools when grounding is not active.
            None if use_grounding else tools,
            use_grounding=use_grounding,
            use_url_context=use_url_context,
        )

        tool_cfg: gtypes.ToolConfig | None = None
        if tool_choice and not use_grounding and gemini_tools:
            if tool_choice == "auto":
                tool_cfg = gtypes.ToolConfig(
                    function_calling_config=gtypes.FunctionCallingConfig(mode="AUTO")
                )
            elif tool_choice == "none":
                tool_cfg = gtypes.ToolConfig(
                    function_calling_config=gtypes.FunctionCallingConfig(mode="NONE")
                )

        thinking_config: gtypes.ThinkingConfig | None = None
        if _is_thinking_model(mid):
            thinking_config = gtypes.ThinkingConfig(
                thinking_budget=_THINKING_BUDGET_TOKENS,
            )

        cfg = gtypes.GenerateContentConfig(
            system_instruction=system_text if system_text else None,
            max_output_tokens=_DEFAULT_MAX_OUTPUT_TOKENS,
            tools=gemini_tools,
            tool_config=tool_cfg,
            thinking_config=thinking_config,
        )

        logger.debug(
            "gemini_native: model=%s tools=%s grounding=%s url_ctx=%s thinking=%s",
            mid,
            len(gemini_tools or []),
            use_grounding,
            use_url_context,
            _is_thinking_model(mid),
        )

        # Accumulated usage totals across all response chunks.
        prompt_tokens = 0
        candidate_tokens = 0
        cached_tokens = 0
        thoughts_tokens = 0

        try:
            for chunk in self._client.models.generate_content_stream(
                model=mid,
                contents=contents,
                config=cfg,
            ):
                # ── Usage metadata ────────────────────────────────────────────
                usage = getattr(chunk, "usage_metadata", None)
                if usage:
                    prompt_tokens = max(prompt_tokens, getattr(usage, "prompt_token_count", 0) or 0)
                    candidate_tokens = max(candidate_tokens, getattr(usage, "candidates_token_count", 0) or 0)
                    cached_tokens = max(cached_tokens, getattr(usage, "cached_content_token_count", 0) or 0)
                    thoughts_tokens = max(thoughts_tokens, getattr(usage, "thoughts_token_count", 0) or 0)

                candidates = getattr(chunk, "candidates", None) or []
                for candidate in candidates:
                    parts = getattr(candidate.content, "parts", None) or []
                    for part in parts:
                        # Text delta.
                        text = getattr(part, "text", None)
                        if text:
                            yield {"type": "delta", "text": text}
                            continue

                        # Thinking (reasoning) delta.
                        thought = getattr(part, "thought", None)
                        if thought and text:
                            yield {"type": "thinking", "text": text}
                            continue

                        # Function call (client-side tool).
                        fc = getattr(part, "function_call", None)
                        if fc is not None:
                            args_dict = dict(fc.args or {})
                            yield {
                                "type": "tool_call",
                                "tool_call": {
                                    "name": fc.name or "",
                                    "arguments": json.dumps(args_dict),
                                    "id": getattr(fc, "id", None) or "",
                                },
                            }
                            continue

                    # ── Grounding metadata (citations) ────────────────────────
                    gm = getattr(candidate, "grounding_metadata", None)
                    if gm:
                        chunks = getattr(gm, "grounding_chunks", None) or []
                        for gchunk in chunks:
                            web = getattr(gchunk, "web", None)
                            if web:
                                url = getattr(web, "uri", None) or getattr(web, "url", None)
                                title = getattr(web, "title", None)
                                if url:
                                    yield {
                                        "type": "citation",
                                        "url": url,
                                        "title": title,
                                        "snippet": None,
                                    }
                                    # Signal server tool used grounding.
                                    yield {
                                        "type": "server_tool_use",
                                        "name": "web_search",
                                        "input": {"query": title or url},
                                        "id": "",
                                    }

        except Exception as exc:
            logger.error("gemini_native: error %s", exc)
            raise ValueError(str(exc)) from exc

        yield {
            "type": "usage",
            "input_tokens": prompt_tokens,
            "output_tokens": candidate_tokens,
            "cached_input_tokens": cached_tokens,
            "cache_creation_input_tokens": 0,
            "reasoning_tokens": thoughts_tokens if thoughts_tokens else None,
        }
