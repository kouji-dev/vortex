"""
Upsert chat models into ``catalog_models`` from ``litellm_catalog_definitions``.

**Anthropic:** ``ANTHROPIC_API_KEY`` (or ``LLM_API_KEY`` fallback). Catalog stores
Claude API ids without the ``anthropic/`` prefix; LiteLLM adds it at completion time.

**OpenAI:** ``LLM_API_KEY`` + ``LLM_API_BASE`` (default api.openai.com). Each
``litellm_model_id`` is validated with ``litellm.get_model_info`` unless the id is
listed as optional (see ``OPTIONAL_LITELLM_MODEL_IDS``) for names not yet in
``litellm.model_cost``.

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
``CHAT_DEFAULT_LITELLM_MODEL`` is the fallback if the catalog row is missing.

Usage (any time):

    cd backend
    pip install -e .
    seed-catalog-models
    # or: python -m ai_portal.scripts.seed_catalog_models --skip-litellm-check
"""

from __future__ import annotations

import argparse
import logging
from typing import Any

from sqlalchemy import delete, inspect, select, update
from sqlalchemy.orm import Session

from ai_portal.catalog_specs import CONFIG_BY_SLUG
from ai_portal.db.session import SessionLocal
from ai_portal.litellm_catalog_definitions import (
    CATALOG_MODEL_DEFINITIONS,
    LEGACY_CATALOG_SLUGS_TO_DEACTIVATE,
    CatalogModelDefinition,
)
from ai_portal.models import CatalogModel
from ai_portal.services.litellm_registry import validate_catalog_litellm_model_id

logger = logging.getLogger(__name__)

_REMOVED_STUB_SLUG = "example-locked-premium"


def _anthropic_meta(litellm_model_id: str, slug: str) -> dict[str, Any]:
    cfg = CONFIG_BY_SLUG.get(slug)
    if cfg is None:
        msg = f"Missing CONFIG_BY_SLUG[{slug!r}]"
        raise KeyError(msg)
    return {
        "provider": "anthropic",
        "model_id": litellm_model_id,
        "api_style": "litellm_anthropic",
        "config": cfg,
    }


def _openai_meta(litellm_model_id: str, slug: str) -> dict[str, Any]:
    cfg = CONFIG_BY_SLUG.get(slug)
    if cfg is None:
        msg = f"Missing CONFIG_BY_SLUG[{slug!r}]"
        raise KeyError(msg)
    return {
        "provider": "openai",
        "model_id": litellm_model_id,
        "api_style": "litellm_openai",
        "config": cfg,
    }


def _row_from_definition(d: CatalogModelDefinition) -> dict[str, Any]:
    if d.provider == "anthropic":
        meta = _anthropic_meta(d.litellm_model_id, d.config_slug)
    elif d.provider == "openai":
        meta = _openai_meta(d.litellm_model_id, d.config_slug)
    else:
        msg = f"Unsupported provider {d.provider!r} for {d.slug}"
        raise ValueError(msg)
    return {
        "slug": d.slug,
        "display_name": d.display_name,
        "description": d.description,
        "litellm_model_id": d.litellm_model_id,
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


def run_seed(
    *,
    dry_run: bool = False,
    skip_litellm_check: bool = False,
) -> None:
    db = SessionLocal()
    try:
        _delete_removed_stub_slug(db)
        added: list[str] = []
        updated: list[str] = []
        for row in _CATALOG_SEED_ROWS:
            if not skip_litellm_check:
                validate_catalog_litellm_model_id(row["litellm_model_id"])
            slug, is_new = _upsert_row(db, row)
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
        "--skip-litellm-check",
        action="store_true",
        help="Do not call litellm.get_model_info on each row (offline / custom forks).",
    )
    args = p.parse_args()
    run_seed(dry_run=args.dry_run, skip_litellm_check=args.skip_litellm_check)


# Export for tests / tooling
__all__ = ["_CATALOG_SEED_ROWS", "run_seed"]

if __name__ == "__main__":
    main()
