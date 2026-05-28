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
from collections.abc import AsyncIterator, Iterator
from typing import Any

import google.genai as genai
import google.genai.types as gtypes

from ai_portal.core.config import Settings
from ai_portal.catalog.providers.base import BaseLlmProvider
from ai_portal.catalog.providers.events import (
    CitationEvent,
    IterationCompleteEvent,
    ProviderErrorEvent,
    ProviderStreamEvent,
    ServerToolUseEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolCallRequestEvent,
    UsageEvent,
)
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

    name = "gemini"
    capabilities = {
        "chat", "streaming", "tools", "vision", "thinking",
        "json_mode", "parallel_tools", "web_search",
    }

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
        finish_reason: str | None = None
        # Grounding state: Gemini's streaming can re-emit the same metadata
        # across chunks, so dedupe by source URL and only fire `server_tool_use`
        # once per response with the actual web_search_queries.
        emitted_citation_urls: set[str] = set()
        server_tool_emitted = False
        all_web_search_queries: list[str] = []

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
                    # Capture finish_reason from last non-None candidate.
                    fr = getattr(candidate, "finish_reason", None)
                    if fr is not None:
                        finish_reason = str(fr)
                    parts = getattr(candidate.content, "parts", None) or []
                    for part in parts:
                        # Thinking (reasoning) delta — check before text because
                        # a thinking part has thought=True and text set to the
                        # reasoning content; checking text first would misroute it.
                        thought = getattr(part, "thought", None)
                        if thought:
                            thinking_text = getattr(part, "text", None)
                            if thinking_text:
                                yield {"type": "thinking", "text": thinking_text}
                            continue

                        # Text delta.
                        text = getattr(part, "text", None)
                        if text:
                            yield {"type": "delta", "text": text}
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

                    # ── Grounding metadata (citations + web_search trace) ─────
                    gm = getattr(candidate, "grounding_metadata", None)
                    if gm:
                        # Accumulate the actual search queries for the single
                        # server_tool_use event we'll emit once we've seen them.
                        queries = list(getattr(gm, "web_search_queries", None) or [])
                        for q in queries:
                            if q and q not in all_web_search_queries:
                                all_web_search_queries.append(q)

                        # Build chunk_index → [supporting text segments] so each
                        # citation gets a meaningful snippet (the model's own
                        # grounded text, which is what Google exposes).
                        chunks = list(getattr(gm, "grounding_chunks", None) or [])
                        snippet_by_idx: dict[int, list[str]] = {}
                        for support in getattr(gm, "grounding_supports", None) or []:
                            seg = getattr(support, "segment", None)
                            seg_text = (getattr(seg, "text", None) or "").strip() if seg else ""
                            if not seg_text:
                                continue
                            for idx in getattr(support, "grounding_chunk_indices", None) or []:
                                snippet_by_idx.setdefault(int(idx), []).append(seg_text)

                        for idx, gchunk in enumerate(chunks):
                            web = getattr(gchunk, "web", None)
                            if not web:
                                continue
                            url = getattr(web, "uri", None) or getattr(web, "url", None)
                            if not url or url in emitted_citation_urls:
                                continue
                            emitted_citation_urls.add(url)
                            title = getattr(web, "title", None)
                            segs = snippet_by_idx.get(idx) or []
                            snippet = (
                                " … ".join(dict.fromkeys(segs))[:500] if segs else None
                            )
                            yield {
                                "type": "citation",
                                "url": url,
                                "title": title,
                                "snippet": snippet,
                            }

                        # One server_tool_use per response, carrying the real
                        # search queries — not a per-chunk repeat. Emit once we
                        # have queries (or once we've seen any chunk if Google
                        # didn't surface queries on this model).
                        if not server_tool_emitted and (all_web_search_queries or emitted_citation_urls):
                            server_tool_emitted = True
                            yield {
                                "type": "server_tool_use",
                                "name": "web_search",
                                "input": {"queries": list(all_web_search_queries)},
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
            "finish_reason": finish_reason,
        }

    # ── Typed async stream ───────────────────────────────────────────────────

    _FINISH_REASON_MAP: dict[str, str] = {
        "STOP": "end_turn",
        "MAX_TOKENS": "max_tokens",
        "SAFETY": "unknown",
        "TOOL": "tool_use",
        "FUNCTION": "tool_use",
    }

    def _translate_dict(self, piece: dict[str, Any]) -> list[ProviderStreamEvent]:
        """Translate a legacy dict event into typed ProviderStreamEvent list."""
        ptype = piece.get("type")

        if ptype == "delta":
            text = piece.get("text", "")
            if text:
                return [ProviderStreamEvent.model_validate(
                    {"type": "text_delta", "text": text}
                )]

        elif ptype == "thinking":
            text = piece.get("text", "")
            if text:
                return [ProviderStreamEvent.model_validate(
                    {"type": "thinking_delta", "text": text}
                )]

        elif ptype == "tool_call":
            tc = piece.get("tool_call", {})
            raw_args = tc.get("arguments", "{}")
            try:
                arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except Exception:
                arguments = {}
            return [ProviderStreamEvent.model_validate({
                "type": "tool_call_request",
                "call_id": tc.get("id", ""),
                "tool_name": tc.get("name", ""),
                "arguments": arguments,
            })]

        elif ptype == "server_tool_use":
            return [ProviderStreamEvent.model_validate({
                "type": "server_tool_use",
                "tool_name": piece.get("name", ""),
                "input": piece.get("input", {}),
            })]

        elif ptype == "citation":
            return [ProviderStreamEvent.model_validate({
                "type": "citation",
                "url": piece.get("url", ""),
                "title": piece.get("title"),
                "snippet": piece.get("snippet"),
            })]

        elif ptype == "usage":
            events: list[ProviderStreamEvent] = [ProviderStreamEvent.model_validate({
                "type": "usage",
                "input_tokens": piece.get("input_tokens", 0) or 0,
                "output_tokens": piece.get("output_tokens", 0) or 0,
                "cached_input_tokens": piece.get("cached_input_tokens", 0) or 0,
                "cache_creation_input_tokens": piece.get("cache_creation_input_tokens", 0) or 0,
                "reasoning_tokens": piece.get("reasoning_tokens") or 0,
            })]
            raw_finish = str(piece.get("finish_reason") or "").upper()
            stop_reason = self._FINISH_REASON_MAP.get(raw_finish, "end_turn")
            events.append(ProviderStreamEvent.model_validate({
                "type": "iteration_complete",
                "stop_reason": stop_reason,
            }))
            return events

        return []

    async def stream(
        self,
        *,
        messages: list[dict],
        model: str,
        settings: dict,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[ProviderStreamEvent]:
        """Async typed stream yielding ProviderStreamEvent."""
        try:
            for piece in self.stream_deltas_with_tools(
                messages,
                model=model,
                tools=tools,
            ):
                for ev in self._translate_dict(piece):
                    yield ev
        except Exception as exc:
            logger.error("gemini_native.stream: error %s", exc)
            yield ProviderStreamEvent.model_validate({
                "type": "provider_error",
                "code": type(exc).__name__,
                "message": str(exc),
            })
