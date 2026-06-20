"""Shared smoke-test auth helper.

Dev auth (the ``Bearer devtoken`` shortcut) was removed in the auth rework. The
backend now validates a real SaaS HS256 JWT whose ``sub`` is the user's ``uuid``.
Smoke tests boot uvicorn/TestClient with::

    DEPLOYMENT_MODE=saas SECRET_KEY=test-secret-key-32-chars-minimum!!

so this helper mints a matching token for the seeded ``dev@localhost`` user.

The dev user is inserted by alembic migration 002 with only its email, so its
``uuid``/``org_id`` may be unset. We backfill both (creating an org if needed)
before signing the token — that is the "create the user if migrations didn't
seed it" path the task calls for, done idempotently.
"""
from __future__ import annotations

import os
import uuid as _uuid

# Must match the SECRET_KEY the smoke server boots with.
SMOKE_SECRET = "test-secret-key-32-chars-minimum!!"
DEV_EMAIL = "dev@localhost"


def _sync_url() -> str:
    url = os.environ["DATABASE_URL"]
    return url.replace("+asyncpg", "+psycopg")


def ensure_dev_user_org() -> tuple[_uuid.UUID, _uuid.UUID]:
    """Ensure ``dev@localhost`` exists with a uuid + org_id. Return (uuid, org_id).

    Idempotent: reuses any existing row/org, only backfilling what's missing.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from ai_portal.auth.model import Org, User

    eng = create_engine(_sync_url())
    with Session(eng) as s:
        user = s.scalars(select(User).where(User.email == DEV_EMAIL)).first()
        if user is None:
            user = User(email=DEV_EMAIL, role="owner")
            s.add(user)
            s.flush()

        if user.uuid is None:
            user.uuid = _uuid.uuid4()

        if user.org_id is None:
            org = s.scalars(select(Org).where(Org.slug == "dev")).first()
            if org is None:
                org = Org(slug="dev", name="Dev Org")
                s.add(org)
                s.flush()
            user.org_id = org.id

        # Smoke endpoints (admin/workers) need an elevated role.
        if user.role not in ("owner", "admin"):
            user.role = "owner"

        s.commit()
        return user.uuid, user.org_id


def mint_dev_bearer(role: str = "owner") -> str:
    """Mint a real access token for the dev user (signed with the smoke secret)."""
    from ai_portal.auth.strategies.jwt import create_access_token

    user_uuid, org_id = ensure_dev_user_org()
    return create_access_token(
        user_uuid=user_uuid,
        org_id=org_id,
        role=role,
        secret=SMOKE_SECRET,
    )


def auth_headers(role: str = "owner") -> dict[str, str]:
    return {"Authorization": f"Bearer {mint_dev_bearer(role)}"}
