"""Background worker that produces cumulative conversation summaries.

Called when total messages cross a window-size boundary so the LLM context
stays bounded while retaining full conversation history via summaries.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.config import get_settings
from ai_portal.db.session import SessionLocal
from ai_portal.models.chat import ChatConversation, ChatMessage

logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM_PROMPT = (
    "You are a concise summarizer. Given a conversation transcript (and optionally "
    "a previous summary), produce a single cumulative summary that captures the key "
    "topics, decisions, and any important details. Keep it under 500 words. "
    "Write in third person."
)


def _call_summary_llm(
    *,
    existing_summary: str | None,
    messages: list[Any],
    settings: Any | None = None,
) -> str | None:
    from ai_portal.services.llm_providers import get_chat_provider

    settings = settings or get_settings()

    transcript_lines: list[str] = []
    if existing_summary:
        transcript_lines.append(f"[Previous summary]\n{existing_summary}\n")
    for m in messages:
        transcript_lines.append(f"{m.role}: {m.content}")
    transcript = "\n".join(transcript_lines)

    llm_messages: list[dict[str, str]] = [
        {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Summarize the following conversation, incorporating any previous "
                "summary:\n\n" + transcript
            ),
        },
    ]

    provider = get_chat_provider(settings)
    result = provider.complete(llm_messages, model=None)
    try:
        return result["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        logger.warning("summary_llm_unexpected_response", extra={"result": result})
        return None


def summarize_conversation(
    conversation_id: int,
    *,
    window_size: int | None = None,
    db: Session | None = None,
) -> None:
    """Build a cumulative summary for messages outside the sliding window."""
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        settings = get_settings()
        window_size = window_size or settings.conversation_window_size

        conv = db.get(ChatConversation, conversation_id)
        if conv is None:
            logger.warning("summarize_skip_missing_conv", extra={"id": conversation_id})
            return

        all_ids: list[int] = list(
            db.scalars(
                select(ChatMessage.id)
                .where(ChatMessage.conversation_id == conv.id)
                .order_by(ChatMessage.id)
            ).all()
        )

        if len(all_ids) <= window_size:
            return

        cutoff_id = all_ids[-window_size]

        outside_msgs = list(
            db.execute(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conv.id)
                .where(ChatMessage.id < cutoff_id)
                .order_by(ChatMessage.id)
            )
            .scalars()
            .all()
        )

        if not outside_msgs:
            return

        new_summary = _call_summary_llm(
            existing_summary=conv.summary,
            messages=outside_msgs,
            settings=settings,
        )
        if new_summary:
            conv.summary = new_summary
            db.commit()
    except Exception:
        logger.exception("summarize_conversation_failed", extra={"id": conversation_id})
    finally:
        if own_session:
            db.close()
