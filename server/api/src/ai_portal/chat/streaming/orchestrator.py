"""orchestrator — public entry point for chat streaming."""

from __future__ import annotations

import logging
import uuid
from typing import Any, AsyncIterator

from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

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
    settings = get_settings()
    return LlmProviderFactory.create(settings, model)


async def stream_turn(
    *,
    user: Any,
    thread_id: int,
    body: dict,
) -> StreamingResponse:
    """Orchestrate a full streaming turn.

    Creates its own DB sessions (never re-uses the auth session) so the
    postgres superuser role is preserved, which naturally bypasses RLS on
    thread_items (no FORCE RLS is applied to that table).
    """
    from sqlalchemy import select  # noqa: PLC0415
    from ai_portal.chat.model import Thread  # noqa: PLC0415
    from ai_portal.core.db.session import SessionLocal  # noqa: PLC0415

    settings = get_settings()

    # Pre-stream session: load thread, gate, turn setup, context assembly.
    # Runs as postgres superuser — bypasses thread_items RLS.
    pre_session = SessionLocal()
    try:
        thread = pre_session.execute(
            select(Thread).where(Thread.id == thread_id)
        ).scalar_one_or_none()
        if thread is None:
            from fastapi import HTTPException, status  # noqa: PLC0415
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Thread not found")

        org_id: uuid.UUID = user.org_id or thread.org_id

        requested_model = (body.get("model") or thread.model or settings.chat_default_api_model or "").strip()
        requested_tools = body.get("tools") or []
        requested_capabilities = body.get("capabilities") or []

        gate_result = turn_gate.evaluate(
            session=pre_session,
            org_id=org_id,
            user_id=user.id,
            requested_model=requested_model,
            requested_tools=requested_tools,
            requested_capabilities=requested_capabilities,
        )

        # Resolve slug → actual API model ID (e.g. "google-gemini-2-5-flash" → "gemini-2.5-flash")
        from ai_portal.catalog.service import resolve_stored_model_to_chat_model  # noqa: PLC0415
        effective_model = resolve_stored_model_to_chat_model(pre_session, gate_result.effective_model)

        user_text = (body.get("text") or "").strip()
        attachments = body.get("attachments") or []
        regenerate_from_turn_id = body.get("regenerate_from_turn_id")
        if isinstance(regenerate_from_turn_id, str):
            import uuid as _uuid  # noqa: PLC0415
            regenerate_from_turn_id = _uuid.UUID(regenerate_from_turn_id)

        turn_ctx = turn_setup.start_or_regenerate(
            session=pre_session,
            thread=thread,
            user_text=user_text,
            attachments=attachments,
            org_id=org_id,
            regenerate_from_turn_id=regenerate_from_turn_id,
        )

        # Commit user message so it appears in context assembly
        pre_session.commit()

        # System prompt
        base_prompt = settings.default_system_prompt or "You are a helpful assistant."
        sys_prompt = system_prompt_mod.compose(
            base_prompt=base_prompt,
            assistant_prompt=None,
            memory_block=None,
            kb_block=None,
            capabilities=gate_result.allowed_capabilities,
        )

        provider_messages = context_assembler.build_provider_messages(
            session=pre_session,
            thread_id=thread_id,
            org_id=org_id,
            system_prompt=sys_prompt,
            window_size=settings.conversation_base_window_size,
        )
    finally:
        pre_session.close()

    provider = _resolve_provider(effective_model)
    turn_id = turn_ctx.turn_id
    max_iter = getattr(settings, "rag_max_tool_iterations", 5)
    cancel_token = register_turn(turn_id)

    async def _generate() -> AsyncIterator[str]:
        from ai_portal.chat.sse import SseEvent  # noqa: PLC0415
        from ai_portal.chat.streaming.item_writer import ItemWriter  # noqa: PLC0415
        from ai_portal.chat.streaming.iteration_loop import _emit  # noqa: PLC0415

        gen_session = SessionLocal()
        writer = ItemWriter(session=gen_session, thread_id=thread_id, org_id=org_id)

        try:
            async for ev in iteration_loop.run(
                provider=provider,
                writer=writer,
                turn_id=turn_id,
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

            end_item = writer.insert_turn_end(
                turn_id=turn_id,
                reason="cancelled" if cancel_token.cancelled else "done",
            )
            yield sse_emitter.encode(_emit(end_item))
            gen_session.commit()
            done_ev = SseEvent.model_validate({"event_type": "done"})
            yield sse_emitter.encode(done_ev)

        except Exception as exc:
            gen_session.rollback()
            events = error_handler.handle_stream_error(
                exc=exc,
                writer=writer,
                turn_id=turn_id,
            )
            for ev in events:
                yield sse_emitter.encode(ev)
            try:
                gen_session.commit()
            except Exception:
                logger.exception("orchestrator: failed to commit error items")

        finally:
            gen_session.close()
            release_turn(turn_id)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
