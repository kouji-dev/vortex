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

from ai_portal.api.deps import get_current_user, get_db
from ai_portal.db.base import Base
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
