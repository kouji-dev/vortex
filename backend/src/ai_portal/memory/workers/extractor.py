"""Background worker: update the single ``is_system`` user profile after each chat turn.

Manual memories (``is_system`` false) are never created or changed here.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.core.config import get_settings
from ai_portal.core.db.session import SessionLocal
from ai_portal.memory.model import UserMemory

logger = logging.getLogger(__name__)

_SYSTEM_PROFILE_PROMPT = (
    "You maintain one concise user profile (persistent facts, preferences, role, tools, "
    "constraints) for use in future chats.\n\n"
    "You are given the current profile text (may be empty) and the latest user + assistant "
    "messages from one turn.\n"
    "Return an UPDATED profile that:\n"
    "- Incorporates only clear new durable facts from the turn\n"
    "- Removes or corrects contradictions when the turn clearly updates older information\n"
    "- Stays compact (aim under ~800 words)\n"
    "- Uses short bullet lines starting with '- ' when listing facts\n\n"
    "Do NOT add or change the profile for low-signal content, including:\n"
    "- Greetings, thanks, small talk, or acknowledgements alone (e.g. the user only said "
    "hello / hi / thanks)\n"
    "- The assistant merely restating or rephrasing the user with no new stable fact\n"
    "- Purely procedural chat (e.g. \"continue\", \"go on\") with no new information about "
    "the user\n\n"
    "If the turn does not add new lasting value about the user, return the current profile "
    "unchanged (verbatim if possible). Prefer no change over inventing or padding the profile."
)


class SystemProfileUpdate(BaseModel):
    profile_text: str = Field(
        default="",
        description=(
            "Full updated profile text. Return empty string if the turn adds no durable user "
            "facts (e.g. greetings only, pure reformulation). Otherwise return the profile, "
            "unchanged verbatim when nothing should change."
        ),
    )


def _call_system_profile_llm(
    *,
    current_profile: str,
    user_message: str,
    assistant_message: str,
    settings: Any | None = None,
) -> str:
    from ai_portal.catalog.providers import get_chat_provider

    settings = settings or get_settings()
    profile_block = current_profile.strip() if current_profile.strip() else "(empty)"
    llm_messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROFILE_PROMPT},
        {
            "role": "user",
            "content": (
                f"[Current profile]\n{profile_block}\n\n"
                f"[Latest turn]\nUser: {user_message}\nAssistant: {assistant_message}"
            ),
        },
    ]
    provider = get_chat_provider(settings)
    try:
        out = provider.complete_structured(
            llm_messages, schema=SystemProfileUpdate, model=None
        )
        return (out.profile_text or "").strip()
    except Exception:
        logger.exception("system_profile_llm_structured_failed")
        return ""


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
        sys_mem = db.scalars(
            select(UserMemory)
            .where(
                UserMemory.user_id == user_id,
                UserMemory.is_system == True,  # noqa: E712
                UserMemory.is_active == True,  # noqa: E712
            )
            .limit(1)
        ).first()

        current = sys_mem.content if sys_mem else ""
        updated = _call_system_profile_llm(
            current_profile=current,
            user_message=user_message,
            assistant_message=assistant_message,
            settings=settings,
        )

        if not updated:
            return

        changed = False
        if sys_mem is None:
            db.add(
                UserMemory(
                    user_id=user_id,
                    content=updated,
                    source="auto",
                    is_system=True,
                    is_active=True,
                )
            )
            changed = True
        elif updated != current:
            sys_mem.content = updated
            changed = True

        if changed:
            db.commit()
    except Exception:
        logger.exception("extract_user_memories_failed", extra={"user_id": user_id})
        if own_session:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        if own_session:
            db.close()
