"""
Dev-only E2E helper endpoints.

Available only when AUTH_MODE=dev.  These routes are registered in main.py
only when auth_mode == "dev" so they are unreachable in production.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.core.db.base import Base
from ai_portal.models import assistant, catalog_model, chat, connector, document, knowledge_base, memory, user, user_portal_api_key  # noqa: F401 — import all models so Base.metadata is fully populated
from ai_portal.models.user import User

router = APIRouter(prefix="/api/e2e", tags=["e2e"])

# Tables that must NOT be truncated (schema metadata + static seed data).
_PRESERVE = {"alembic_version", "catalog_models"}

_E2E_DB_NAME = "ai_portal_e2e"


def _require_e2e_database(db: Session) -> None:
    """Refuse destructive E2E helpers unless connected to the isolated E2E database."""
    name = db.execute(text("SELECT current_database()")).scalar_one()
    if name != _E2E_DB_NAME:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=(
                f"E2E purge refused: connected database is {name!r}, expected {_E2E_DB_NAME!r}. "
                "Point the API at the E2E Postgres (see docker-compose.e2e.yml and ./scripts/e2e-up.sh)."
            ),
        )


@router.post("/purge", status_code=200)
def purge_e2e_data(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """
    Truncate all application tables except ``alembic_version`` and
    ``catalog_models``.  Restores the dev seed user afterwards so
    subsequent requests can still authenticate.

    Playwright global-teardown calls this after the test run.
    Only runs when ``current_database()`` is ``ai_portal_e2e`` so a misconfigured
    ``E2E_API_URL`` cannot wipe the main dev database.
    """
    _require_e2e_database(db)
    tables = [
        t.name
        for t in reversed(Base.metadata.sorted_tables)
        if t.name not in _PRESERVE
    ]
    if not tables:
        return {"status": "nothing to purge"}

    quoted = ", ".join(f'"{t}"' for t in tables)
    db.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))

    # Re-seed the dev user so auth still works in the next run.
    db.execute(
        text(
            "INSERT INTO users (email) VALUES ('dev@localhost') "
            "ON CONFLICT (email) DO NOTHING"
        )
    )
    db.commit()
    return {"status": "purged", "tables": quoted}


class E2eSeedSystemMemoryBody(BaseModel):
    content: str = Field(default="E2E seeded profile", max_length=500_000)


@router.post("/seed-system-memory", status_code=status.HTTP_201_CREATED)
def e2e_seed_system_memory(
    body: E2eSeedSystemMemoryBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """Create or replace the dev user's single ``is_system`` profile row (E2E DB only)."""
    _require_e2e_database(db)
    from ai_portal.models.memory import UserMemory
    existing = db.scalars(
        select(UserMemory)
        .where(
            UserMemory.user_id == user.id,
            UserMemory.is_system == True,  # noqa: E712
        )
        .limit(1)
    ).first()
    profile_text = (body.content or "").strip() or "E2E seeded profile"
    if existing is not None:
        existing.content = profile_text
        existing.is_active = True
        existing.source = "auto"
    else:
        db.add(
            UserMemory(
                user_id=user.id,
                content=profile_text,
                source="auto",
                is_system=True,
                is_active=True,
            )
        )
    db.commit()
    return {"ok": True}


class E2eSeedToolStreamBody(BaseModel):
    conversation_id: int


@router.post("/seed-tool-stream", status_code=status.HTTP_201_CREATED)
def e2e_seed_tool_stream(
    body: E2eSeedToolStreamBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    Seed a conversation with a user + assistant message pair, and return
    the SSE text that a tool-using stream would have produced.

    Used by Playwright E2E tests to replay a pre-built SSE stream without
    hitting a real LLM or external tools.
    """
    _require_e2e_database(db)
    from ai_portal.models.chat import ChatMessage as ChatMessageModel
    import json as _json

    # Seed user message
    user_msg = ChatMessageModel(
        conversation_id=body.conversation_id,
        role="user",
        content="What is the latest news?",
    )
    db.add(user_msg)

    # Seed assistant reply
    assistant_msg = ChatMessageModel(
        conversation_id=body.conversation_id,
        role="assistant",
        content="Here is the latest news based on my web search.",
    )
    db.add(assistant_msg)
    db.commit()

    def _e(payload: dict) -> str:
        return f"data: {_json.dumps(payload)}\n\n"

    sse_events = (
        _e({"type": "item_start", "item": {"kind": "thinking"}})
        + _e({"type": "item_start", "item": {"kind": "memory", "count": 1}})
        + _e({"type": "item_done", "item": {"kind": "memory", "status": "done"}})
        + _e({"type": "item_start", "item": {"kind": "tool_call", "tool": "web_search", "params": {"query": "latest news"}}})
        + _e({"type": "item_done", "item": {"kind": "tool_call", "tool": "web_search", "status": "done"}})
        + _e({"type": "item_start", "item": {"kind": "tool_call", "tool": "search_knowledge_base", "params": {"query": "news"}}})
        + _e({"type": "item_done", "item": {"kind": "tool_call", "tool": "search_knowledge_base", "status": "done"}})
        + _e({"type": "item_done", "item": {"kind": "thinking"}})
        + _e({"type": "delta", "text": "Here is the latest news based on my web search."})
        + _e({"type": "done", "message_id": assistant_msg.id})
    )

    return {"sse": sse_events, "message_id": str(assistant_msg.id), "conversation_id": str(body.conversation_id)}
