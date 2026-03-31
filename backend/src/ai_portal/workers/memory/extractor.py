"""Background worker that extracts persistent user-profile facts from conversations.

Uses LLM structured output to manage memories: add new facts, update
existing ones, and remove outdated/contradicted ones — all in one call.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.config import get_settings
from ai_portal.db.session import SessionLocal
from ai_portal.models.memory import UserMemory

logger = logging.getLogger(__name__)

_EXTRACTION_SYSTEM_PROMPT = (
    "You manage persistent facts about the user. You are given:\n"
    "1. The user's existing memories (with IDs)\n"
    "2. A new conversation turn\n\n"
    "Decide what changes to make:\n"
    "- add: genuinely new facts not already captured\n"
    "- update: existing facts that should be refined, corrected, or merged "
    "(provide the ID and the new wording)\n"
    "- remove: IDs of facts that are now outdated or contradicted\n\n"
    "Be conservative — only act on clear, persistent user traits, preferences, "
    "role, tools, constraints, etc. If nothing changed, return empty lists."
)


class MemoryUpdate(BaseModel):
    id: int
    content: str


class MemoryDelta(BaseModel):
    add: list[str] = Field(default_factory=list)
    update: list[MemoryUpdate] = Field(default_factory=list)
    remove: list[int] = Field(default_factory=list)


def _call_extraction_llm(
    *,
    user_message: str,
    assistant_message: str,
    existing_memories: list[dict[str, Any]],
    settings: Any | None = None,
) -> MemoryDelta:
    from ai_portal.services.llm_providers import get_chat_provider

    settings = settings or get_settings()

    if existing_memories:
        mem_lines = "\n".join(
            f"- [id={m['id']}] {m['content']}" for m in existing_memories
        )
        memories_block = f"[Existing memories]\n{mem_lines}"
    else:
        memories_block = "[Existing memories]\n(none)"

    llm_messages: list[dict[str, str]] = [
        {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{memories_block}\n\n"
                f"[New conversation turn]\n"
                f"User: {user_message}\n"
                f"Assistant: {assistant_message}"
            ),
        },
    ]

    provider = get_chat_provider(settings)
    try:
        return provider.complete_structured(
            llm_messages, schema=MemoryDelta, model=None
        )
    except Exception:
        logger.exception("extraction_llm_structured_failed")
        return MemoryDelta()


def extract_user_memories(
    user_id: int,
    *,
    user_message: str,
    assistant_message: str,
    db: Session | None = None,
) -> None:
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        settings = get_settings()

        existing = list(
            db.scalars(
                select(UserMemory).where(
                    UserMemory.user_id == user_id,
                    UserMemory.is_active == True,  # noqa: E712
                )
            ).all()
        )
        existing_dicts = [{"id": m.id, "content": m.content} for m in existing]
        existing_by_id = {m.id: m for m in existing}

        delta = _call_extraction_llm(
            user_message=user_message,
            assistant_message=assistant_message,
            existing_memories=existing_dicts,
            settings=settings,
        )

        if not delta.add and not delta.update and not delta.remove:
            return

        for fact in delta.add:
            stripped = fact.strip()
            if stripped:
                db.add(
                    UserMemory(
                        user_id=user_id,
                        content=stripped,
                        source="auto",
                        is_active=True,
                    )
                )

        for upd in delta.update:
            mem = existing_by_id.get(upd.id)
            if mem and upd.content.strip():
                mem.content = upd.content.strip()

        for mem_id in delta.remove:
            mem = existing_by_id.get(mem_id)
            if mem:
                mem.is_active = False

        db.commit()
    except Exception:
        logger.exception("extract_user_memories_failed", extra={"user_id": user_id})
    finally:
        if own_session:
            db.close()
