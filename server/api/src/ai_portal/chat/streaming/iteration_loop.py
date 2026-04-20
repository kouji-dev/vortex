"""iteration_loop — LLM + tool agentic loop yielding SseEvents.

Yields SseEvent objects for each item that completes during a streaming turn.
This is an async generator: callers do ``async for event in run(...): ...``.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncIterator, Any

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
from ai_portal.chat.cost_calculator import compute_llm_cost
from ai_portal.chat.item_kinds import ItemKind, ItemRole, ItemStatus
from ai_portal.chat.items import ThreadItemModel
from ai_portal.chat.model import ThreadItem
from ai_portal.chat.sse import SseDoneEvent, SseEvent, SseItemEvent
from ai_portal.chat.streaming.cancellation import CancelToken
from ai_portal.chat.streaming.item_writer import ItemWriter
from ai_portal.chat.streaming.sse_emitter import encode
from ai_portal.chat.tool_outcome import ToolCallOutcome
from ai_portal.chat.tool_service import dispatch_tool

logger = logging.getLogger(__name__)


def _build_tool_schemas(allowed: list[str]) -> list[dict]:
    """Return tool schemas for the allowed tool names from the registry.

    Calls get_tool_definitions with no kb_ids / capabilities — it will return
    the schemas for client-dispatch tools (web_search, fetch_webpage) when those
    names appear in the allowed list.  Falls back to empty list on any error.
    """
    if not allowed:
        return []
    try:
        from ai_portal.tools.registry import get_tool_definitions  # noqa: PLC0415
        # get_tool_definitions(kb_ids, model_id, capabilities) returns all active
        # tool schemas.  We pass no kb_ids and no model so only generic tools
        # (web_search / fetch_webpage) that don't require capabilities are returned,
        # then filter to what is actually allowed for this turn.
        all_schemas = get_tool_definitions(kb_ids=[], model_id=None, capabilities=None)
        return [s for s in all_schemas if s.get("name") in allowed]
    except Exception:
        logger.exception("_build_tool_schemas: failed to load tool definitions")
        return []


def _row_to_dict(item: ThreadItem) -> dict:
    """Convert a ThreadItem ORM row to a dict suitable for ThreadItemModel.model_validate."""
    created_at = item.created_at
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    if hasattr(created_at, "tzinfo") and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    return {
        "id": item.id,
        "thread_id": item.thread_id,
        "turn_id": str(item.turn_id),
        "kind": item.kind.value if hasattr(item.kind, "value") else item.kind,
        "role": item.role.value if item.role and hasattr(item.role, "value") else item.role,
        "status": item.status.value if hasattr(item.status, "value") else item.status,
        "provider": item.provider,
        "model": item.model,
        "cost_usd": str(item.cost_usd) if item.cost_usd is not None else None,
        "cost_estimated": item.cost_estimated,
        "latency_ms": item.latency_ms,
        "parent_item_id": item.parent_item_id,
        "started_at": item.started_at,
        "finished_at": item.finished_at,
        "created_at": created_at,
        "data": item.data or {},
    }


def _emit(item: ThreadItem) -> SseEvent:
    """Wrap a completed ThreadItem in an SseItemEvent."""
    item_dict = _row_to_dict(item)
    item_model = ThreadItemModel.model_validate(item_dict)
    return SseEvent.model_validate({"event_type": "item", "item": item_model})


async def run(
    *,
    provider: Any,
    writer: ItemWriter,
    turn_id: uuid.UUID,
    provider_messages: list[dict],
    model: str,
    settings: Any = None,
    allowed_tools: list[str],
    max_iterations: int,
    cancel_token: CancelToken | None = None,
    org_id: uuid.UUID | None = None,
    user_id: int | None = None,
):
    """Async generator: stream one or more LLM iterations, yielding SseEvents.

    Handles text, thinking, tool calls, server tool uses, citations, and usage.
    Stops when stop_reason == "end_turn" or max_iterations is reached.
    """
    tool_schemas = _build_tool_schemas(allowed_tools)
    messages = list(provider_messages)
    iteration = 0

    while iteration <= max_iterations:
        # Check cancellation
        if cancel_token and cancel_token.cancelled:
            logger.info("iteration_loop: cancelled at iteration=%d", iteration)
            cancelled_count = await writer.cancel_turn_items(turn_id=turn_id)
            logger.info("iteration_loop: cancelled %d streaming items", cancelled_count)
            return

        logger.info("iteration_loop: LLM call iteration=%d model=%r", iteration, model)

        # Start an llm_call item
        llm_item = await writer.start_llm_call(
            turn_id=turn_id, model=model, iteration_index=iteration
        )
        yield _emit(llm_item)

        # Accumulators for this iteration
        text_item_id: int | None = None
        thinking_item_id: int | None = None
        tool_request: ToolCallRequestEvent | None = None
        server_tool: ServerToolUseEvent | None = None
        usage: UsageEvent | None = None
        stop_reason: str = "unknown"
        citations: list[CitationEvent] = []
        had_error = False

        try:
            async for ev_wrapper in provider.stream(
                messages=messages,
                model=model,
                settings=settings or {},
                tools=tool_schemas if tool_schemas else None,
            ):
                # Unwrap the discriminated-union root
                ev = ev_wrapper.root if hasattr(ev_wrapper, "root") else ev_wrapper

                # Check cancellation inside the stream
                if cancel_token and cancel_token.cancelled:
                    logger.info("iteration_loop: cancelled mid-stream at iteration=%d", iteration)
                    break

                if isinstance(ev, TextDeltaEvent):
                    if text_item_id is None:
                        text_item = await writer.start_text(turn_id=turn_id)
                        text_item_id = text_item.id
                        yield _emit(text_item)
                    await writer.append_text_delta(text_item_id, ev.text)

                elif isinstance(ev, ThinkingDeltaEvent):
                    if thinking_item_id is None:
                        think_item = await writer.start_thinking(turn_id=turn_id)
                        thinking_item_id = think_item.id
                        yield _emit(think_item)
                    await writer.append_text_delta(thinking_item_id, ev.text)

                elif isinstance(ev, ToolCallRequestEvent):
                    tool_request = ev

                elif isinstance(ev, ServerToolUseEvent):
                    server_tool = ev

                elif isinstance(ev, CitationEvent):
                    citations.append(ev)

                elif isinstance(ev, UsageEvent):
                    usage = ev

                elif isinstance(ev, IterationCompleteEvent):
                    stop_reason = ev.stop_reason

                elif isinstance(ev, ProviderErrorEvent):
                    raise RuntimeError(f"{ev.code}: {ev.message}")

        except Exception as exc:
            logger.exception("iteration_loop: error at iteration=%d", iteration)
            had_error = True
            await writer.fail_llm_call(item_id=llm_item.id, error=str(exc))
            raise

        # Finalize text/thinking items
        if text_item_id is not None:
            final_text = await writer.finalize_text(text_item_id)
            yield _emit(final_text)

        if thinking_item_id is not None:
            final_think = await writer.finalize_thinking(thinking_item_id)
            yield _emit(final_think)

        # Emit citation items
        for cit in citations:
            cit_item = await writer.insert_citation(
                turn_id=turn_id,
                url=cit.url,
                title=cit.title,
                snippet=cit.snippet,
                parent_item_id=text_item_id,
            )
            yield _emit(cit_item)

        # Finish llm_call item
        if usage:
            cost_result = compute_llm_cost(
                model=model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cached_input_tokens=usage.cached_input_tokens,
                cache_creation_input_tokens=usage.cache_creation_input_tokens,
                reasoning_tokens=usage.reasoning_tokens,
            )
            cost_usd = cost_result.cost_usd
            cost_estimated = cost_result.estimated
        else:
            cost_usd = Decimal("0")
            cost_estimated = True

        if not had_error:
            done_llm = await writer.finish_llm_call(
                item_id=llm_item.id,
                input_tokens=usage.input_tokens if usage else 0,
                output_tokens=usage.output_tokens if usage else 0,
                cached_input_tokens=usage.cached_input_tokens if usage else 0,
                cache_creation_input_tokens=usage.cache_creation_input_tokens if usage else 0,
                reasoning_tokens=usage.reasoning_tokens if usage else 0,
                cost_usd=cost_usd,
                cost_estimated=cost_estimated,
            )
            yield _emit(done_llm)

        # Server tool use — just record and emit (provider executed it)
        if server_tool is not None:
            srv_item = await writer.start_server_tool(
                turn_id=turn_id,
                tool_name=server_tool.tool_name,
                provider="provider",
                input_payload=server_tool.input,
            )
            done_srv = await writer.finish_server_tool(
                item_id=srv_item.id,
                cost_usd=Decimal("0"),
                cost_estimated=True,
            )
            yield _emit(done_srv)

        # Tool call dispatch
        if tool_request is not None and iteration < max_iterations:
            tool_item = await writer.start_tool_call(
                turn_id=turn_id,
                tool_name=tool_request.tool_name,
                provider=None,
                params=tool_request.arguments,
            )
            yield _emit(tool_item)

            # Dispatch the tool
            outcome: ToolCallOutcome = await dispatch_tool(
                tool_name=tool_request.tool_name,
                call_id=tool_request.call_id,
                arguments=tool_request.arguments,
                org_id=str(org_id) if org_id else "",
                user_id=user_id,
            )

            done_tool = await writer.finish_tool_call(
                item_id=tool_item.id,
                result_snippet=outcome.result_snippet,
                error=outcome.error,
                cost_usd=outcome.cost_usd or Decimal("0"),
                cost_estimated=True,
                latency_ms=outcome.latency_ms,
            )
            yield _emit(done_tool)

            # Append tool result to messages for next iteration
            messages.append({
                "role": "assistant", "content": "",
                "tool_calls": [{
                    "id": tool_request.call_id, "type": "function",
                    "function": {
                        "name": tool_request.tool_name,
                        "arguments": json.dumps(tool_request.arguments),
                    },
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_request.call_id,
                "content": outcome.result_snippet or outcome.error or "",
            })
            iteration += 1
            continue

        # No tool call or stop_reason == "end_turn" — we're done
        logger.info("iteration_loop: done stop_reason=%r iteration=%d", stop_reason, iteration)
        break
