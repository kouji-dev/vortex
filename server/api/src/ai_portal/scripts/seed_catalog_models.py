"""
Upsert chat models into ``catalog_models`` from ``catalog_model_definitions``.

**Anthropic:** ``ANTHROPIC_API_KEY``. Catalog stores Claude API ids without the
``anthropic/`` prefix; LangChain ``ChatAnthropic`` uses those ids directly.

**OpenAI:** ``OPENAI_API_KEY`` + ``OPENAI_API_BASE`` (default api.openai.com). Each
``api_model_id`` is checked for non-empty values; optional ids skip stricter
checks (see ``OPTIONAL_CATALOG_API_MODEL_IDS``).

Re-run anytime; rows are matched by ``slug`` and updated in place. Legacy slugs
from the previous catalog are set ``is_active=false`` so they disappear from the
picker without deleting history.

**After a DB reset** (e.g. ``docker compose down -v`` then ``up -d``), apply schema
then seed — same order as local dev / CI:

    cd backend
    alembic upgrade head
    seed-catalog-models
    # or: python -m ai_portal.scripts.seed_catalog_models

New conversations prefer catalog slug ``anthropic-claude-haiku-4-5`` when that row
is active (see ``default_conversation_model._DEFAULT_CATALOG_SLUG_PRIORITY``);
``CHAT_DEFAULT_API_MODEL`` (or ``CHAT_DEFAULT_MODEL`` / ``CHAT_MODEL``) is the
fallback if the catalog row is missing.

Usage (any time):

    cd backend
    pip install -e .
    seed-catalog-models
    # or: python -m ai_portal.scripts.seed_catalog_models --skip-model-validation
"""

from __future__ import annotations

import argparse
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import delete, inspect, select, update
from sqlalchemy.orm import Session

from ai_portal.catalog.definitions import (
    CATALOG_MODEL_DEFINITIONS,
    LEGACY_CATALOG_SLUGS_TO_DEACTIVATE,
    CatalogModelDefinition,
)
from ai_portal.catalog.specs import CONFIG_BY_SLUG
from ai_portal.core.db.session import SessionLocal
from ai_portal.catalog.model import CatalogModel
from ai_portal.catalog.service import validate_catalog_model_id
from ai_portal.auth.model import Org

# Import all models so SQLAlchemy metadata has every table registered
# (needed to resolve FK references like catalog_models.org_id → orgs.id)
import ai_portal.models  # noqa: F401

logger = logging.getLogger(__name__)

_REMOVED_STUB_SLUG = "example-locked-premium"


def _anthropic_meta(api_model_id: str, slug: str) -> dict[str, Any]:
    cfg = CONFIG_BY_SLUG.get(slug)
    if cfg is None:
        msg = f"Missing CONFIG_BY_SLUG[{slug!r}]"
        raise KeyError(msg)
    return {
        "provider": "anthropic",
        "model_id": api_model_id,
        "api_style": "langchain_anthropic",
        "config": cfg,
    }


def _openai_meta(api_model_id: str, slug: str) -> dict[str, Any]:
    cfg = CONFIG_BY_SLUG.get(slug)
    if cfg is None:
        msg = f"Missing CONFIG_BY_SLUG[{slug!r}]"
        raise KeyError(msg)
    return {
        "provider": "openai",
        "model_id": api_model_id,
        "api_style": "langchain_openai",
        "config": cfg,
    }


def _gemini_meta(api_model_id: str, slug: str) -> dict[str, Any]:
    cfg = CONFIG_BY_SLUG.get(slug)
    if cfg is None:
        msg = f"Missing CONFIG_BY_SLUG[{slug!r}]"
        raise KeyError(msg)
    return {
        "provider": "google",
        "model_id": api_model_id,
        "api_style": "langchain_google_genai",
        "config": cfg,
    }


def _row_from_definition(d: CatalogModelDefinition) -> dict[str, Any]:
    if d.provider == "anthropic":
        meta = _anthropic_meta(d.api_model_id, d.config_slug)
    elif d.provider == "openai":
        meta = _openai_meta(d.api_model_id, d.config_slug)
    elif d.provider == "google":
        meta = _gemini_meta(d.api_model_id, d.config_slug)
    else:
        msg = f"Unsupported provider {d.provider!r} for {d.slug}"
        raise ValueError(msg)
    return {
        "slug": d.slug,
        "display_name": d.display_name,
        "description": d.description,
        "api_model_id": d.api_model_id,
        "effort": d.effort,
        "is_active": True,
        "sort_order": d.sort_order,
        "requires_entitlement": d.requires_entitlement,
        "request_access_url": d.request_access_url,
        "catalog_metadata": meta,
    }


def _catalog_seed_rows() -> list[dict[str, Any]]:
    return [_row_from_definition(d) for d in CATALOG_MODEL_DEFINITIONS]


_CATALOG_SEED_ROWS: list[dict[str, Any]] = _catalog_seed_rows()


def _ensure_default_org(db: Session) -> UUID:
    """Resolve org for catalog rows: ``default`` slug, else first org, else insert default org.

    Matches migration backfills that use ``orgs.slug = 'default'`` (see ``022_auth_overhaul`` /
    ``023_multitenancy``). When the DB is empty (e.g. fresh self-hosted before setup), inserts
    the same default org row as the initial migration.
    """
    org = db.scalars(select(Org).where(Org.slug == "default").limit(1)).first()
    if org is not None:
        return org.id
    org = db.scalars(select(Org).order_by(Org.created_at.asc()).limit(1)).first()
    if org is not None:
        logger.info(
            "catalog seed: no org with slug 'default'; using first org %s (%s)",
            org.id,
            org.slug,
        )
        return org.id
    org = Org(slug="default", name="Default Org")
    db.add(org)
    db.flush()
    logger.info(
        "catalog seed: created default org %s (slug=default) for catalog_models",
        org.id,
    )
    return org.id


def _upsert_row(db: Session, row: dict[str, Any]) -> tuple[str, bool]:
    slug = row["slug"]
    existing = db.scalars(
        select(CatalogModel).where(CatalogModel.slug == slug).limit(1)
    ).first()
    if existing is None:
        db.add(CatalogModel(**row))
        return slug, True
    for key, val in row.items():
        setattr(existing, key, val)
    return slug, False


def _delete_removed_stub_slug(db: Session) -> None:
    bind = db.get_bind()
    if bind is None or not inspect(bind).has_table(CatalogModel.__tablename__):
        return
    db.execute(delete(CatalogModel).where(CatalogModel.slug == _REMOVED_STUB_SLUG))


def _deactivate_legacy_slugs(db: Session) -> None:
    if not LEGACY_CATALOG_SLUGS_TO_DEACTIVATE:
        return
    db.execute(
        update(CatalogModel)
        .where(CatalogModel.slug.in_(LEGACY_CATALOG_SLUGS_TO_DEACTIVATE))
        .values(is_active=False)
    )


def _get_default_org_id(db: Session):
    """Return the default org's UUID, or None if the orgs table doesn't exist yet."""
    from ai_portal.auth.model import Org
    try:
        org = db.scalars(select(Org).where(Org.slug == "default").limit(1)).first()
        return org.id if org else None
    except Exception:
        return None


def run_seed(
    *,
    dry_run: bool = False,
    skip_model_validation: bool = False,
) -> None:
    db = SessionLocal()
    try:
        org_id = _ensure_default_org(db)
        _delete_removed_stub_slug(db)
        default_org_id = _get_default_org_id(db)
        added: list[str] = []
        updated: list[str] = []
        for row in _CATALOG_SEED_ROWS:
            if not skip_model_validation:
                validate_catalog_model_id(row["api_model_id"])
            # Inject org_id for new rows (existing rows already have it set)
            row_with_org = {**row, "org_id": default_org_id} if default_org_id else row
            slug, is_new = _upsert_row(db, row_with_org)
            if is_new:
                added.append(slug)
            else:
                updated.append(slug)
        _deactivate_legacy_slugs(db)
        if dry_run:
            db.rollback()
            logger.info(
                "dry_run: would upsert %d rows (add %s, update %s)",
                len(_CATALOG_SEED_ROWS),
                added,
                updated,
            )
            return
        db.commit()
        logger.info(
            "catalog seed done: added=%s updated=%s",
            added,
            updated,
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute upserts but roll back (no DB writes).",
    )
    p.add_argument(
        "--skip-model-validation",
        action="store_true",
        help="Do not validate each catalog model id (offline / custom forks).",
    )
    args = p.parse_args()
    run_seed(dry_run=args.dry_run, skip_model_validation=args.skip_model_validation)


# Export for tests / tooling
__all__ = ["_CATALOG_SEED_ROWS", "run_seed"]

if __name__ == "__main__":
    main()
