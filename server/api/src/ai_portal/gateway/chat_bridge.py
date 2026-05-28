"""Bridge from the legacy ChatProvider stream to the gateway observability stack.

The chat module's :mod:`ai_portal.chat.streaming.iteration_loop` uses the
legacy :class:`ChatProvider` shape (``provider.stream(messages=, model=,
settings=, tools=)``) which yields vendor-shaped
:class:`ProviderStreamEvent` chunks. Migrating chat to the canonical
:class:`LLMRequest` / :class:`StreamChunk` types is a follow-up beyond
this phase; the immediate goal is to make every chat LLM call show up in
``request_traces`` so the gateway observability UI can see them next to
the compat-endpoint traffic.

:func:`stream_chat_legacy` accepts the legacy provider + ``stream()`` kwargs,
yields chunks 1:1, and emits a trace row via the installed
:class:`GatewayFacade` at end of stream. If no facade is installed, the
wrapper degrades to a pass-through — chat keeps working in environments
that haven't booted the gateway (e.g. unit tests).
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from ai_portal.gateway.facade import Actor, get_default_facade
from ai_portal.gateway.traces.writer import TraceRecord

logger = logging.getLogger(__name__)


async def stream_chat_legacy(
    *,
    provider: Any,
    messages: list[dict],
    model: str,
    settings: dict | None = None,
    tools: list[dict] | None = None,
    org_id: uuid.UUID | None = None,
    user_id: int | None = None,
    route: str = "chat.stream",
) -> AsyncIterator[Any]:
    """Wrap legacy ``provider.stream(...)`` with trace emission.

    Yields each ``ProviderStreamEvent`` produced by the provider. After the
    stream closes (success or error), emits one :class:`TraceRecord` to the
    installed gateway facade so chat completions are visible alongside
    compat-endpoint traffic in ``request_traces``.

    The wrapper is best-effort: any error in trace emission is logged and
    swallowed. The original stream's exception (if any) is re-raised.
    """
    started = time.monotonic()
    status = "ok"
    error: str | None = None
    tokens_in = tokens_out = 0
    tokens_cache_read = tokens_cache_write = 0

    try:
        async for ev_wrapper in provider.stream(
            messages=messages, model=model, settings=settings or {}, tools=tools,
        ):
            inner = ev_wrapper.root if hasattr(ev_wrapper, "root") else ev_wrapper
            ev_type = getattr(inner, "type", None)
            if ev_type == "usage":
                tokens_in = getattr(inner, "input_tokens", 0) or tokens_in
                tokens_out = getattr(inner, "output_tokens", 0) or tokens_out
                tokens_cache_read = (
                    getattr(inner, "cached_input_tokens", 0) or tokens_cache_read
                )
                tokens_cache_write = (
                    getattr(inner, "cache_creation_input_tokens", 0)
                    or tokens_cache_write
                )
            elif ev_type == "provider_error":
                # Mirror iteration_loop semantics: a provider_error event is a
                # fatal error for the iteration, but iteration_loop raises
                # downstream, so we just record status and yield the event.
                status = "error"
                error = f"{getattr(inner, 'code', '?')}: {getattr(inner, 'message', '')}"
            yield ev_wrapper
    except Exception as exc:  # noqa: BLE001
        status = "error"
        error = str(exc)
        raise
    finally:
        latency_ms = int((time.monotonic() - started) * 1000)
        _emit_trace(
            route=route,
            org_id=org_id,
            user_id=user_id,
            model=model,
            status=status,
            error=error,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_cache_read=tokens_cache_read,
            tokens_cache_write=tokens_cache_write,
            provider_name=getattr(provider, "name", "unknown"),
        )


def _emit_trace(
    *,
    route: str,
    org_id: uuid.UUID | None,
    user_id: int | None,
    model: str,
    status: str,
    error: str | None,
    latency_ms: int,
    tokens_in: int,
    tokens_out: int,
    tokens_cache_read: int,
    tokens_cache_write: int,
    provider_name: str,
) -> None:
    """Best-effort trace write. Silent no-op when no facade is installed."""
    if org_id is None:
        return  # No tenant — skip trace (unit-test sessions without orgs).
    try:
        facade = get_default_facade()
    except RuntimeError:
        return  # No facade bound — chat keeps working without observability.

    actor = Actor(
        org_id=org_id,
        user_id=user_id,
        kind="user" if user_id is not None else "service",
    )
    rec = TraceRecord(
        org_id=org_id,
        route=route,
        actor_json=actor.to_dict(),
        model_requested=model,
        model_used=model,
        provider=provider_name,
        status=status,
        latency_ms=latency_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tokens_cache_read=tokens_cache_read,
        tokens_cache_write=tokens_cache_write,
        cost_cents=0.0,  # cost calc already lives in iteration_loop
        cache_hit=False,
        error=error,
    )
    try:
        facade.cfg.emit_trace(rec)
    except Exception:  # noqa: BLE001
        logger.exception("chat_bridge: emit_trace failed")


__all__ = ["stream_chat_legacy"]
