"""Sync Gemini models from the live Google API into the catalog.

Usage:
    python -m ai_portal.scripts.sync_gemini_models [--min-version 2.5] [--dry-run]

Fetches all models from the Google Generative AI API, filters to those
supporting generateContent with version >= min_version, and upserts them
into catalog_models. Older/removed models are deactivated automatically.
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


def _parse_version(name: str) -> tuple[int, ...]:
    """Extract numeric version tuple from model name, e.g. 'gemini-2.5-flash' → (2, 5)."""
    m = re.search(r"gemini-(\d+)\.?(\d*)", name)
    if not m:
        return (0,)
    major = int(m.group(1))
    minor = int(m.group(2)) if m.group(2) else 0
    return (major, minor)


def _min_version_tuple(s: str) -> tuple[int, ...]:
    parts = s.split(".")
    return tuple(int(p) for p in parts)


def _slug_from_name(name: str) -> str:
    """'models/gemini-2.5-flash' → 'google-gemini-2-5-flash'"""
    bare = name.removeprefix("models/")
    return "google-" + re.sub(r"[.\s]", "-", bare)


def _display_name(model) -> str:
    dn = getattr(model, "display_name", "") or ""
    if dn:
        return dn
    bare = getattr(model, "name", "").removeprefix("models/")
    return bare.replace("-", " ").title()


def _effort(name: str) -> str:
    n = name.lower()
    if "pro" in n:
        return "high"
    if "flash" in n or "lite" in n:
        return "low"
    return "medium"


def _catalog_metadata(model, api_model_id: str) -> dict:
    return {
        "provider": "google",
        "model_id": api_model_id,
        "api_style": "langchain_google_genai",
        "config": {
            "reasoning": {"supported": False, "efforts_available": [], "default_effort": None},
            "sampling": {
                "temperature": {"default": 0.7, "min": 0.0, "max": 2.0},
                "max_output_tokens": {"default": 8192, "max": 65536},
            },
            "features": {"streaming": True, "vision": True, "tools": True, "json_mode": True},
        },
    }


def sync(min_version: tuple[int, ...], dry_run: bool) -> None:
    from google import genai  # type: ignore[import]

    settings = get_settings()
    if not settings.gemini_api_key.strip():
        logger.error("GEMINI_API_KEY is not set — add it to config.yaml or env before running.")
        sys.exit(1)

    client = genai.Client(api_key=settings.gemini_api_key)

    logger.info("Fetching model list from Google API...")
    all_models = list(client.models.list())
    logger.info("Total models returned: %d", len(all_models))

    # Suffixes/prefixes that indicate non-text-generation models
    _EXCLUDE_PATTERNS = ("tts", "image", "computer-use", "computer_use")
    _EXCLUDE_PREFIXES = ("gemma-", "lyria-", "imagen-", "veo-")

    # Filter: must support generateContent, version >= min_version, and be a text LLM
    eligible = []
    for m in all_models:
        actions = getattr(m, "supported_actions", []) or []
        if "generateContent" not in actions:
            continue
        name = getattr(m, "name", "")
        bare = name.removeprefix("models/").lower()
        if any(bare.startswith(p) for p in _EXCLUDE_PREFIXES):
            continue
        if any(p in bare for p in _EXCLUDE_PATTERNS):
            continue
        ver = _parse_version(name)
        if ver >= min_version:
            eligible.append(m)

    logger.info(
        "Models with generateContent and version >= %s: %d",
        ".".join(str(v) for v in min_version),
        len(eligible),
    )

    for m in sorted(eligible, key=lambda x: x.name):
        logger.info("  %s | %s", m.name, getattr(m, "display_name", ""))

    if dry_run:
        logger.info("Dry run — no DB changes made.")
        return

    engine = create_engine(settings.database_url)
    with Session(engine) as db:
        # Resolve org_id
        org_row = db.execute(text("SELECT id FROM orgs WHERE slug = 'default' LIMIT 1")).fetchone()
        if org_row is None:
            org_row = db.execute(text("SELECT id FROM orgs ORDER BY created_at ASC LIMIT 1")).fetchone()
        org_id = str(org_row[0]) if org_row else None

        eligible_slugs: list[str] = []
        sort_base = 300

        for i, m in enumerate(sorted(eligible, key=lambda x: x.name)):
            api_model_id = m.name.removeprefix("models/")
            slug = _slug_from_name(m.name)
            eligible_slugs.append(slug)

            existing = db.execute(
                text("SELECT id FROM catalog_models WHERE slug = :slug"),
                {"slug": slug},
            ).fetchone()

            metadata = _catalog_metadata(m, api_model_id)

            if existing is None:
                logger.info("INSERT %s (%s)", slug, api_model_id)
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
                        "display_name": _display_name(m),
                        "description": getattr(m, "description", "") or "",
                        "api_model_id": api_model_id,
                        "effort": _effort(api_model_id),
                        "sort_order": sort_base + i,
                        "is_active": True,
                        "requires_entitlement": False,
                        "request_access_url": None,
                        "catalog_metadata": json.dumps(metadata),
                    },
                )
            else:
                logger.info("UPDATE %s (%s)", slug, api_model_id)
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
                        "api_model_id": api_model_id,
                        "display_name": _display_name(m),
                        "catalog_metadata": json.dumps(metadata),
                        "slug": slug,
                    },
                )

        # Deactivate google-gemini-* models not in the eligible set
        db.execute(
            text("""
                UPDATE catalog_models
                SET is_active = false
                WHERE slug LIKE 'google-gemini-%'
                  AND slug != ALL(:keep_slugs)
            """),
            {"keep_slugs": eligible_slugs},
        )
        logger.info("Deactivated stale google-gemini-* models not in live list.")

        db.commit()
        logger.info("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Gemini models from Google API to catalog.")
    parser.add_argument("--min-version", default="2.5", help="Minimum Gemini version (default: 2.5)")
    parser.add_argument("--dry-run", action="store_true", help="Print models without writing to DB")
    args = parser.parse_args()

    min_ver = _min_version_tuple(args.min_version)
    sync(min_version=min_ver, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
