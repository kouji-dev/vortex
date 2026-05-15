"""orchestrator — public entry point for chat streaming."""

from __future__ import annotations

import logging
import uuid
from typing import Any, AsyncIterator

from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ai_portal.catalog.providers import LlmProviderFactory
from ai_portal.chat import memory_extractor, title_generator
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
from ai_portal.core.realtime import publish_user_event

logger = logging.getLogger(__name__)


def _resolve_provider(model: str) -> Any:
    settings = get_settings()
    return LlmProviderFactory.create(settings, model)


async def _generate_and_publish_title(
    *,
    provider: Any,
    model: str,
    user_text: str,
    thread_id: int,
    user_id: int,
    org_id: uuid.UUID,
) -> None:
    """Background task: title the conversation, persist, publish via Redis."""
    import asyncio as _asyncio  # noqa: PLC0415
    from ai_portal.chat.model import Thread  # noqa: PLC0415
    from ai_portal.core.db.session import SessionLocal  # noqa: PLC0415

    try:
        title = await _asyncio.to_thread(
            title_generator.generate_title, provider, model, user_text
        )
        if not title:
            return
        sess = SessionLocal()
        try:
            t = sess.get(Thread, thread_id)
            if t is None or not title_generator.needs_title(t.title):
                return
            t.title = title
            sess.commit()
        finally:
            sess.close()
        await publish_user_event(
            user_id,
            "conversation_title_changed",
            {"conversation_id": thread_id, "title": title},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("title_generation_failed", extra={"err": str(exc)})


async def _extract_and_persist_memories(
    *,
    provider: Any,
    model: str,
    user_text: str,
    thread_id: int,
    turn_id: uuid.UUID,
    user_id: int,
    org_id: uuid.UUID,
) -> None:
    """Background task: extract user-fact memories from the just-finished turn."""
    import asyncio as _asyncio  # noqa: PLC0415
    from sqlalchemy import select as _select  # noqa: PLC0415

    from ai_portal.chat.item_kinds import ItemKind  # noqa: PLC0415
    from ai_portal.chat.model import ThreadItem  # noqa: PLC0415
    from ai_portal.core.db.session import SessionLocal  # noqa: PLC0415
    from ai_portal.memory.model import UserMemory  # noqa: PLC0415

    try:
        sess = SessionLocal()
        try:
            # Collect the assistant's text reply for this turn (may be split
            # across multiple `assistant_text` items — concatenate in order).
            text_items = sess.execute(
                _select(ThreadItem)
                .where(
                    ThreadItem.thread_id == thread_id,
                    ThreadItem.turn_id == turn_id,
                    ThreadItem.kind == ItemKind.assistant_text,
                )
                .order_by(ThreadItem.id)
            ).scalars().all()
            assistant_text = "\n\n".join(
                (t.data or {}).get("text", "") for t in text_items
            ).strip()

            existing = sess.execute(
                _select(UserMemory)
                .where(UserMemory.user_id == user_id, UserMemory.is_active.is_(True))
                .order_by(UserMemory.id.desc())
                .limit(50)
            ).scalars().all()
            existing_facts = [m.content for m in existing]
        finally:
            sess.close()

        if not assistant_text:
            return

        new_facts = await _asyncio.to_thread(
            memory_extractor.extract_memories,
            provider, model, user_text, assistant_text, existing_facts,
        )
        if not new_facts:
            return

        sess = SessionLocal()
        try:
            for fact in new_facts:
                sess.add(UserMemory(
                    org_id=org_id, user_id=user_id, content=fact,
                    source="auto", is_system=False, is_active=True,
                ))
            sess.commit()
        finally:
            sess.close()

        await publish_user_event(
            user_id,
            "memories_changed",
            {"added": len(new_facts)},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_extraction_failed", extra={"err": str(exc)})


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
        requested_tools = list(body.get("tools") or [])
        requested_capabilities = list(body.get("capabilities") or [])

        # Conversation-level capability toggles (persisted in thread.settings)
        # are the source of truth — the frontend's per-turn body doesn't
        # forward them. Expand them into both `requested_capabilities` (drives
        # the system prompt) and `requested_tools` (drives web_search /
        # fetch_webpage schema injection), still subject to RBAC in the gate.
        conv_caps = (thread.settings.capabilities if thread.settings else None)
        if conv_caps is not None:
            for cap_name in ("reflection", "research"):
                if getattr(conv_caps, cap_name, False) and cap_name not in requested_capabilities:
                    requested_capabilities.append(cap_name)
            if getattr(conv_caps, "reflection", False) or getattr(conv_caps, "research", False):
                for tool_name in ("web_search", "fetch_webpage"):
                    if tool_name not in requested_tools:
                        requested_tools.append(tool_name)

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

        user_text = (body.get("text") or body.get("content") or "").strip()
        attachments = body.get("attachments") or []
        thread_title_at_start = thread.title
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

        # Snapshot the persisted user_message while its session is alive — the
        # SSE generator runs after pre_session.close(), so reading ORM
        # attributes there would hit a detached instance.
        user_message_sse: str | None = None
        if turn_ctx.user_message_item is not None:
            from ai_portal.chat.streaming.iteration_loop import _emit  # noqa: PLC0415
            user_message_sse = sse_emitter.encode(_emit(turn_ctx.user_message_item))

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

    # SimpleNamespace lets tools/registry's getattr(caps, "reflection") /
    # getattr(caps, "research") checks fire without leaking the ORM instance
    # past pre_session.close().
    from types import SimpleNamespace  # noqa: PLC0415
    capabilities_for_tools = SimpleNamespace(
        reflection="reflection" in gate_result.allowed_capabilities,
        research="research" in gate_result.allowed_capabilities,
    )

    # Fire-and-forget conversation-title generation. Runs in parallel with the
    # streamed reply; result is pushed to the user's global SSE channel.
    if (
        regenerate_from_turn_id is None
        and title_generator.needs_title(thread_title_at_start)
        and user_text
    ):
        import asyncio as _asyncio  # noqa: PLC0415
        _asyncio.create_task(_generate_and_publish_title(
            provider=provider,
            model=effective_model,
            user_text=user_text,
            thread_id=thread_id,
            user_id=user.id,
            org_id=org_id,
        ))

    async def _generate() -> AsyncIterator[str]:
        from ai_portal.chat.sse import SseEvent  # noqa: PLC0415
        from ai_portal.chat.streaming.item_writer import ItemWriter  # noqa: PLC0415
        from ai_portal.chat.streaming.iteration_loop import _emit  # noqa: PLC0415

        gen_session = SessionLocal()
        writer = ItemWriter(session=gen_session, thread_id=thread_id, org_id=org_id)

        try:
            # Emit the persisted user_message so the client's cache holds the
            # canonical row (replacing its optimistic placeholder) without a
            # post-stream refetch. None for regenerations: the row already
            # exists from the original turn.
            if user_message_sse is not None:
                yield user_message_sse

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
                capabilities=capabilities_for_tools,
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

            # Fire-and-forget memory extraction on success. Skipped on
            # regenerations (turn already exists; nothing new for the user
            # said) and on cancellation.
            if (
                not cancel_token.cancelled
                and regenerate_from_turn_id is None
                and user_text
            ):
                import asyncio as _asyncio  # noqa: PLC0415
                _asyncio.create_task(_extract_and_persist_memories(
                    provider=provider,
                    model=effective_model,
                    user_text=user_text,
                    thread_id=thread_id,
                    turn_id=turn_id,
                    user_id=user.id,
                    org_id=org_id,
                ))

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
