"""Background worker that produces cumulative conversation summaries.

Called when total messages cross a window-size boundary so the LLM context
stays bounded while retaining full conversation history via summaries.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.core.config import get_settings
from ai_portal.core.db.session import SessionLocal
from ai_portal.chat.model import Thread, ThreadItem

logger = logging.getLogger(__name__)

_INITIAL_SUMMARY_PROMPT = (
    "You are a concise summarizer. Given a conversation transcript, produce a "
    "summary that captures the key topics, decisions, and any important details. "
    "Keep it under 500 words. Write in third person."
)

_ENHANCE_SUMMARY_PROMPT = (
    "You are a concise summarizer. You are given an existing conversation summary "
    "and a batch of new messages. Produce a single enhanced summary that incorporates "
    "the new information into the existing summary. Preserve important details from "
    "the existing summary while integrating new topics, decisions, and context. "
    "Keep it under 500 words. Write in third person."
)


def _format_transcript(messages: list[Any]) -> str:
    parts: list[str] = []
    for m in messages:
        role = (m.role or "system").value if hasattr(m.role, "value") else (m.role or "system")
        text = m.data.get("text", "") if isinstance(m.data, dict) else ""
        if text:
            parts.append(f"{role}: {text}")
    return "\n".join(parts)


def _call_summary_llm(
    *,
    existing_summary: str | None,
    messages: list[Any],
    settings: Any | None = None,
) -> str | None:
    from ai_portal.catalog.providers import get_chat_provider

    settings = settings or get_settings()
    transcript = _format_transcript(messages)

    if existing_summary:
        llm_messages: list[dict[str, str]] = [
            {"role": "system", "content": _ENHANCE_SUMMARY_PROMPT},
            {
                "role": "user",
                "content": (
                    f"[Existing summary]\n{existing_summary}\n\n"
                    f"[New messages]\n{transcript}"
                ),
            },
        ]
    else:
        llm_messages = [
            {"role": "system", "content": _INITIAL_SUMMARY_PROMPT},
            {
                "role": "user",
                "content": f"Summarize the following conversation:\n\n{transcript}",
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
    summary_interval: int | None = None,
    db: Session | None = None,
) -> None:
    """Build a cumulative summary for messages outside the sliding window.

    Once the conversation exceeds the base window, only the last
    ``summary_interval`` messages are kept in context; everything older
    gets folded into the cumulative summary.
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        settings = get_settings()
        summary_interval = summary_interval or settings.conversation_summary_interval

        conv = db.get(Thread, conversation_id)
        if conv is None:
            logger.warning("summarize_skip_missing_conv", extra={"id": conversation_id})
            return

        all_ids: list[int] = list(
            db.scalars(
                select(ThreadItem.id)
                .where(ThreadItem.thread_id == conv.id)
                .order_by(ThreadItem.id)
            ).all()
        )

        if len(all_ids) <= summary_interval:
            return

        cutoff_id = all_ids[-summary_interval]

        if conv.summary:
            prev_cutoff_idx = max(0, len(all_ids) - 2 * summary_interval)
            prev_cutoff_id = all_ids[prev_cutoff_idx]
            new_msgs = list(
                db.execute(
                    select(ThreadItem)
                    .where(ThreadItem.thread_id == conv.id)
                    .where(ThreadItem.id >= prev_cutoff_id)
                    .where(ThreadItem.id < cutoff_id)
                    .order_by(ThreadItem.id)
                )
                .scalars()
                .all()
            )
        else:
            new_msgs = list(
                db.execute(
                    select(ThreadItem)
                    .where(ThreadItem.thread_id == conv.id)
                    .where(ThreadItem.id < cutoff_id)
                    .order_by(ThreadItem.id)
                )
                .scalars()
                .all()
            )

        if not new_msgs:
            return

        new_summary = _call_summary_llm(
            existing_summary=conv.summary,
            messages=new_msgs,
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
