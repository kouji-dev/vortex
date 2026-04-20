"""orchestrator — public entry point for chat streaming.

``stream_turn`` is the sole public API:
- Validates quota and RBAC via turn_gate.evaluate
- Sets up the turn via turn_setup.new_turn
- Assembles context via context_assembler
- Runs the LLM + tool loop via iteration_loop.run
- Handles errors via error_handler
- Returns a StreamingResponse
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, AsyncIterator

from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.catalog.providers import LlmProviderFactory
from ai_portal.chat.streaming import (
    context_assembler,
    error_handler,
    iteration_loop,
    sse_emitter,
    system_prompt as system_prompt_mod,
    turn_gate,
    turn_setup,
)
from ai_portal.chat.streaming.cancellation import register_turn, release_turn
from ai_portal.core.config import get_settings

logger = logging.getLogger(__name__)


def _resolve_provider(model: str) -> Any:
    """Resolve a provider for the given model string."""
    settings = get_settings()
    return LlmProviderFactory.create(settings, model)


async def stream_turn(
    *,
    session: AsyncSession,
    user: Any,
    thread_id: int,
    body: dict,
) -> StreamingResponse:
    """Orchestrate a full streaming turn and return a StreamingResponse.

    Args:
        session: An async SQLAlchemy session (caller manages lifecycle).
        user: The authenticated user object with .id, .org_id, .role.
        thread_id: The thread (conversation) ID.
        body: Request body dict with keys: text, attachments, model,
              optionally: capabilities, tools, regenerate_turn_id.
    """
    from sqlalchemy import select  # noqa: PLC0415
    from ai_portal.chat.model import Thread  # noqa: PLC0415

    settings = get_settings()

    # Resolve thread
    thread = (await session.execute(
        select(Thread).where(Thread.id == thread_id)
    )).scalar_one_or_none()
    if thread is None:
        from fastapi import HTTPException, status  # noqa: PLC0415
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Thread not found")

    org_id: uuid.UUID = user.org_id or thread.org_id

    # Resolve model
    requested_model = (body.get("model") or thread.model or settings.chat_default_api_model or "").strip()
    requested_tools = body.get("tools") or []
    requested_capabilities = body.get("capabilities") or []

    # Gate: quota + RBAC (may raise HTTPException)
    gate_result = await turn_gate.evaluate(
        session=session,
        org_id=org_id,
        user_id=user.id,
        requested_model=requested_model,
        requested_tools=requested_tools,
        requested_capabilities=requested_capabilities,
    )

    effective_model = gate_result.effective_model

    # Turn setup
    user_text = (body.get("text") or "").strip()
    attachments = body.get("attachments") or []
    regenerate_from_turn_id = body.get("regenerate_from_turn_id")
    if isinstance(regenerate_from_turn_id, str):
        import uuid as _uuid  # noqa: PLC0415
        regenerate_from_turn_id = _uuid.UUID(regenerate_from_turn_id)

    turn_ctx = await turn_setup.start_or_regenerate(
        session=session,
        thread=thread,
        user_text=user_text,
        attachments=attachments,
        org_id=org_id,
        regenerate_from_turn_id=regenerate_from_turn_id,
    )

    # Use the writer from turn_ctx — avoids creating a duplicate ItemWriter
    writer = turn_ctx.writer

    # Commit the user_message now so it is persisted even if the LLM call fails.
    # The streaming generator manages its own transaction for the assistant items.
    await session.commit()

    # Register cancellation token
    cancel_token = register_turn(turn_ctx.turn_id)

    # System prompt
    base_prompt = settings.default_system_prompt or "You are a helpful assistant."
    sys_prompt = system_prompt_mod.compose(
        base_prompt=base_prompt,
        assistant_prompt=None,
        memory_block=None,
        kb_block=None,
        capabilities=gate_result.allowed_capabilities,
    )

    # Context assembly
    provider_messages = await context_assembler.build_provider_messages(
        session=session,
        thread_id=thread_id,
        org_id=org_id,
        system_prompt=sys_prompt,
        window_size=settings.conversation_base_window_size,
    )

    # Resolve provider
    provider = _resolve_provider(effective_model)

    max_iter = getattr(settings, "rag_max_tool_iterations", 5)

    async def _generate() -> AsyncIterator[str]:
        from ai_portal.chat.sse import SseEvent  # noqa: PLC0415
        from ai_portal.chat.streaming.iteration_loop import _emit  # noqa: PLC0415

        try:
            async for ev in iteration_loop.run(
                provider=provider,
                writer=writer,
                turn_id=turn_ctx.turn_id,
                provider_messages=provider_messages,
                model=effective_model,
                settings=settings,
                allowed_tools=gate_result.allowed_tools,
                max_iterations=max_iter,
                cancel_token=cancel_token,
                org_id=org_id,
                user_id=user.id,
            ):
                yield sse_emitter.encode(ev)

            # Success path: emit turn_end, commit, then emit done
            end_item = await writer.insert_turn_end(
                turn_id=turn_ctx.turn_id,
                reason="cancelled" if cancel_token.cancelled else "done",
            )
            yield sse_emitter.encode(_emit(end_item))
            await session.commit()
            done_ev = SseEvent.model_validate({"event_type": "done"})
            yield sse_emitter.encode(done_ev)

        except Exception as exc:
            # Error path: rollback first, then let error_handler write its items
            await session.rollback()
            events = await error_handler.handle_stream_error(
                exc=exc,
                writer=writer,
                turn_id=turn_ctx.turn_id,
            )
            for ev in events:
                yield sse_emitter.encode(ev)
            # Commit the error/turn_end items written by error_handler
            try:
                await session.commit()
            except Exception:
                logger.exception("orchestrator: failed to commit error items")

        finally:
            release_turn(turn_ctx.turn_id)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
