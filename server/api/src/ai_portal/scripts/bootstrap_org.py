"""
Bootstrap the first org and owner user for a self-hosted instance.

Usage:
    bootstrap-org --org-name "Acme Corp" --org-slug acme --owner-email admin@acme.com
    bootstrap-org --org-name "Acme Corp" --org-slug acme --owner-email admin@acme.com --owner-password s3cr3t

Idempotent: if an org with the given slug already exists, prints a message and
exits 0 without modifying anything.

Designed for self-hosted bootstrap (DEPLOYMENT_MODE=selfhosted) before the
SetupGuardMiddleware would otherwise block all API routes.
"""

from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

# Import all models so SQLAlchemy metadata is fully populated
import ai_portal.models  # noqa: F401

logger = logging.getLogger(__name__)


def bootstrap(
    db: Session,
    *,
    org_name: str,
    org_slug: str,
    owner_email: str,
    owner_password: str | None = None,
) -> tuple:
    """Core logic — callable from tests or CLI.

    Returns (org, user). Raises ValueError if the org already exists.
    Caller is responsible for commit/rollback.
    """
    from ai_portal.auth.model import Org, User
    from ai_portal.auth.password import hash_password

    existing = db.scalars(
        select(Org).where(Org.slug == org_slug).limit(1)
    ).first()
    if existing is not None:
        raise ValueError(f"Org with slug {org_slug!r} already exists (id={existing.id})")

    org = Org(slug=org_slug, name=org_name)
    db.add(org)
    db.flush()  # populate org.id

    hashed: str | None = None
    if owner_password is not None:
        hashed = hash_password(owner_password)

    user = User(
        email=owner_email,
        org_id=org.id,
        role="owner",
        is_active=True,
        is_verified=True,
        hashed_password=hashed,
    )
    db.add(user)
    db.flush()  # populate user.id

    return org, user


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    p = argparse.ArgumentParser(
        description="Bootstrap first org and owner user for a self-hosted instance."
    )
    p.add_argument("--org-name", required=True, help="Display name for the org.")
    p.add_argument("--org-slug", required=True, help="URL-safe slug (unique).")
    p.add_argument("--owner-email", required=True, help="Owner user email address.")
    p.add_argument(
        "--owner-password",
        default=None,
        help="Plaintext password for the owner (bcrypt-hashed before storage). "
        "Omit to create a password-less user (SSO / invite flow).",
    )
    args = p.parse_args()

    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        try:
            org, user = bootstrap(
                db,
                org_name=args.org_name,
                org_slug=args.org_slug,
                owner_email=args.owner_email,
                owner_password=args.owner_password,
            )
        except ValueError as exc:
            logger.info("%s", exc)
            sys.exit(0)

        db.commit()
        logger.info("bootstrap: org created id=%s slug=%s", org.id, org.slug)
        logger.info("bootstrap: owner created email=%s role=%s", user.email, user.role)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
