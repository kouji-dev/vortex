"""
Dev-only E2E helper endpoints.

Available only when AUTH_MODE=dev.  These routes are registered in main.py
only when auth_mode == "dev" so they are unreachable in production.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ai_portal.api.deps import get_current_user, get_db
from ai_portal.db.base import Base
from ai_portal.models import assistant, catalog_model, chat, connector, document, knowledge_base, memory, user, user_portal_api_key  # noqa: F401 — import all models so Base.metadata is fully populated
from ai_portal.models.user import User

router = APIRouter(prefix="/api/e2e", tags=["e2e"])

# Tables that must NOT be truncated (schema metadata + static seed data).
_PRESERVE = {"alembic_version", "catalog_models"}


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
    """
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
