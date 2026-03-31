"""Background worker that extracts persistent user-profile facts from conversations."""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.config import get_settings
from ai_portal.db.session import SessionLocal
from ai_portal.models.memory import UserMemory

logger = logging.getLogger(__name__)

_EXTRACTION_SYSTEM_PROMPT = (
    "You extract persistent facts about the user from a conversation turn. "
    "Return a JSON array of short strings — each one a standalone fact worth "
    "remembering long-term (preferences, role, tools, constraints, etc.). "
    "If there is nothing worth remembering, return an empty array []."
)


def _call_extraction_llm(
    user_message: str,
    assistant_message: str,
    settings: Any | None = None,
) -> list[str]:
    from ai_portal.services.llm_providers import get_chat_provider

    settings = settings or get_settings()

    llm_messages: list[dict[str, str]] = [
        {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"User said:\n{user_message}\n\n"
                f"Assistant replied:\n{assistant_message}\n\n"
                "Extract persistent facts as a JSON array of strings."
            ),
        },
    ]

    provider = get_chat_provider(settings)
    result = provider.complete(llm_messages, model=None)
    try:
        raw = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        logger.warning("extraction_llm_unexpected_response", extra={"result": result})
        return []

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except (json.JSONDecodeError, TypeError):
        logger.warning("extraction_llm_json_parse_failed", extra={"raw": raw})
    return []


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
        facts = _call_extraction_llm(user_message, assistant_message, settings)
        if not facts:
            return

        existing = list(
            db.scalars(
                select(UserMemory).where(UserMemory.user_id == user_id)
            ).all()
        )
        existing_lower = {m.content.lower() for m in existing}

        for fact in facts:
            if fact.lower() in existing_lower:
                continue
            db.add(
                UserMemory(
                    user_id=user_id,
                    content=fact,
                    source="auto",
                    is_active=True,
                )
            )
            existing_lower.add(fact.lower())

        db.commit()
    except Exception:
        logger.exception("extract_user_memories_failed", extra={"user_id": user_id})
    finally:
        if own_session:
            db.close()
