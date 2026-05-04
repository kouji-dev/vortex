"""Sync Anthropic Claude models from the live API into the catalog.

Usage:
    python -m ai_portal.scripts.sync_anthropic_models [--dry-run]

Fetches all models from the Anthropic API, filters to Claude chat models,
and upserts them into catalog_models with up-to-date capability metadata.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from ai_portal.core.config import get_settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# Models with extended thinking / reasoning tokens
_THINKING_MODELS = frozenset({
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-opus-4-7",
})

# Effort levels for reasoning models
_REASONING_EFFORTS = ["minimal", "low", "medium", "high"]


def _slug_from_id(model_id: str) -> str:
    """'claude-haiku-4-5-20251001' → 'anthropic-claude-haiku-4-5-20251001'"""
    return f"anthropic-{model_id}"


def _display_name(model_id: str) -> str:
    bare = model_id.replace("-", " ").title()
    return f"Claude {bare}" if not bare.lower().startswith("claude") else bare


def _effort(model_id: str) -> str:
    n = model_id.lower()
    if "opus" in n:
        return "high"
    if "sonnet" in n:
        return "medium"
    return "low"


def _supports_thinking(model_id: str) -> bool:
    bare = re.sub(r"-\d{8}$", "", model_id)  # strip date snapshot suffix
    return bare in _THINKING_MODELS


def _catalog_metadata(model_id: str, display_name: str) -> dict:
    thinking = _supports_thinking(model_id)
    return {
        "provider": "anthropic",
        "model_id": model_id,
        "api_style": "anthropic_native",
        "config": {
            "reasoning": {
                "supported": thinking,
                "efforts_available": _REASONING_EFFORTS if thinking else [],
                "default_effort": "medium" if thinking else None,
            },
            "sampling": {
                "temperature": {"min": 0.0, "max": 1.0, "default": 1.0},
                "max_output_tokens": {"min": 1, "max": 128_000, "default": 16_384},
            },
            "features": {
                "streaming": True,
                "vision": True,
                "tools": True,
                "json_mode": True,
                "thinking": thinking,
            },
        },
    }


def sync(dry_run: bool) -> None:
    settings = get_settings()
    if not settings.anthropic_api_key.strip():
        logger.error("ANTHROPIC_API_KEY is not set — add it to config.yaml or env before running.")
        sys.exit(1)

    try:
        import anthropic  # type: ignore[import]
    except ImportError:
        logger.error("anthropic package not installed.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    logger.info("Fetching model list from Anthropic API...")
    all_models = list(client.models.list())
    logger.info("Total models returned: %d", len(all_models))

    eligible = [
        m for m in all_models
        if m.id.startswith("claude-")
    ]
    logger.info("Claude chat models: %d", len(eligible))
    for m in sorted(eligible, key=lambda x: x.id):
        logger.info("  %s", m.id)

    if dry_run:
        logger.info("Dry run — no DB changes made.")
        return

    engine = create_engine(settings.database_url)
    with Session(engine) as db:
        org_row = db.execute(text("SELECT id FROM orgs WHERE slug = 'default' LIMIT 1")).fetchone()
        if org_row is None:
            org_row = db.execute(text("SELECT id FROM orgs ORDER BY created_at ASC LIMIT 1")).fetchone()
        org_id = str(org_row[0]) if org_row else None

        eligible_slugs: list[str] = []
        sort_base = 10

        for i, m in enumerate(sorted(eligible, key=lambda x: x.id)):
            slug = _slug_from_id(m.id)
            eligible_slugs.append(slug)
            dn = getattr(m, "display_name", None) or _display_name(m.id)
            metadata = _catalog_metadata(m.id, dn)

            existing = db.execute(
                text("SELECT id FROM catalog_models WHERE slug = :slug"),
                {"slug": slug},
            ).fetchone()

            if existing is None:
                logger.info("INSERT %s", slug)
                db.execute(
                    text("""
                        INSERT INTO catalog_models
                            (org_id, slug, display_name, description, api_model_id,
                             effort, sort_order, is_active, requires_entitlement,
                             request_access_url, catalog_metadata)
                        VALUES
                            (:org_id, :slug, :display_name, :description, :api_model_id,
                             :effort, :sort_order, :is_active, :requires_entitlement,
                             :request_access_url, CAST(:catalog_metadata AS jsonb))
                    """),
                    {
                        "org_id": org_id,
                        "slug": slug,
                        "display_name": dn,
                        "description": f"Anthropic {dn}. API id ``{m.id}``.",
                        "api_model_id": m.id,
                        "effort": _effort(m.id),
                        "sort_order": sort_base + i,
                        "is_active": True,
                        "requires_entitlement": False,
                        "request_access_url": None,
                        "catalog_metadata": json.dumps(metadata),
                    },
                )
            else:
                logger.info("UPDATE %s", slug)
                db.execute(
                    text("""
                        UPDATE catalog_models
                        SET api_model_id = :api_model_id,
                            display_name  = :display_name,
                            is_active     = true,
                            catalog_metadata = CAST(:catalog_metadata AS jsonb)
                        WHERE slug = :slug
                    """),
                    {
                        "api_model_id": m.id,
                        "display_name": dn,
                        "catalog_metadata": json.dumps(metadata),
                        "slug": slug,
                    },
                )

        db.commit()
        logger.info("Done. %d models synced.", len(eligible_slugs))


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Anthropic Claude models to catalog.")
    parser.add_argument("--dry-run", action="store_true", help="Print models without writing to DB")
    args = parser.parse_args()
    sync(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
