"""Insert Gemini catalog models; disable all OpenAI catalog models

Revision ID: 026_gemini_models_disable_openai
Revises: 025_chat_uploads
Create Date: 2026-04-08

Data migration:
  - Inserts 8 Google Gemini models into catalog_models (upsert by slug).
  - Sets is_active=False for all rows with slug LIKE 'openai-%'.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "026_gemini_models_disable_openai"
down_revision = "025_chat_uploads"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Gemini catalog rows to insert
# ---------------------------------------------------------------------------

_GEMINI_ROWS = [
    {
        "slug": "google-gemini-2-5-flash-lite",
        "display_name": "Gemini 2.5 Flash Lite",
        "description": (
            "Google Gemini 2.5 Flash Lite — cheapest Gemini tier; fast, high-throughput. "
            "API id ``gemini-2.5-flash-lite``."
        ),
        "api_model_id": "gemini-2.5-flash-lite",
        "effort": "low",
        "sort_order": 200,
        "is_active": True,
        "requires_entitlement": False,
        "request_access_url": None,
        "catalog_metadata": {
            "provider": "google",
            "model_id": "gemini-2.5-flash-lite",
            "api_style": "langchain_google_genai",
            "config": {
                "reasoning": {"supported": False, "efforts_available": [], "default_effort": None},
                "sampling": {"temperature": {"default": 0.7, "min": 0.0, "max": 2.0}, "max_output_tokens": {"default": 8192, "max": 8192}},
                "features": {"streaming": True, "vision": True, "tools": True, "json_mode": True},
            },
        },
    },
    {
        "slug": "google-gemini-2-5-flash",
        "display_name": "Gemini 2.5 Flash",
        "description": (
            "Google Gemini 2.5 Flash — fast, cost-efficient multimodal model. "
            "API id ``gemini-2.5-flash``."
        ),
        "api_model_id": "gemini-2.5-flash",
        "effort": "low",
        "sort_order": 210,
        "is_active": True,
        "requires_entitlement": False,
        "request_access_url": None,
        "catalog_metadata": {
            "provider": "google",
            "model_id": "gemini-2.5-flash",
            "api_style": "langchain_google_genai",
            "config": {
                "reasoning": {"supported": False, "efforts_available": [], "default_effort": None},
                "sampling": {"temperature": {"default": 0.7, "min": 0.0, "max": 2.0}, "max_output_tokens": {"default": 8192, "max": 65536}},
                "features": {"streaming": True, "vision": True, "tools": True, "json_mode": True},
            },
        },
    },
    {
        "slug": "google-gemini-2-5-pro",
        "display_name": "Gemini 2.5 Pro",
        "description": (
            "Google Gemini 2.5 Pro — advanced reasoning and coding. "
            "API id ``gemini-2.5-pro``."
        ),
        "api_model_id": "gemini-2.5-pro",
        "effort": "high",
        "sort_order": 220,
        "is_active": True,
        "requires_entitlement": False,
        "request_access_url": None,
        "catalog_metadata": {
            "provider": "google",
            "model_id": "gemini-2.5-pro",
            "api_style": "langchain_google_genai",
            "config": {
                "reasoning": {"supported": False, "efforts_available": [], "default_effort": None},
                "sampling": {"temperature": {"default": 0.7, "min": 0.0, "max": 2.0}, "max_output_tokens": {"default": 8192, "max": 65536}},
                "features": {"streaming": True, "vision": True, "tools": True, "json_mode": True},
            },
        },
    },
    {
        "slug": "google-gemini-3-flash",
        "display_name": "Gemini 3 Flash",
        "description": (
            "Google Gemini 3 Flash — next-gen fast model. "
            "API id ``gemini-3-flash``."
        ),
        "api_model_id": "gemini-3-flash",
        "effort": "low",
        "sort_order": 230,
        "is_active": True,
        "requires_entitlement": False,
        "request_access_url": None,
        "catalog_metadata": {
            "provider": "google",
            "model_id": "gemini-3-flash",
            "api_style": "langchain_google_genai",
            "config": {
                "reasoning": {"supported": False, "efforts_available": [], "default_effort": None},
                "sampling": {"temperature": {"default": 0.7, "min": 0.0, "max": 2.0}, "max_output_tokens": {"default": 8192, "max": 65536}},
                "features": {"streaming": True, "vision": True, "tools": True, "json_mode": True},
            },
        },
    },
    {
        "slug": "google-gemini-3-1-flash-lite",
        "display_name": "Gemini 3.1 Flash Lite",
        "description": (
            "Google Gemini 3.1 Flash Lite — cheapest 3.x tier. "
            "API id ``gemini-3.1-flash-lite``."
        ),
        "api_model_id": "gemini-3.1-flash-lite",
        "effort": "low",
        "sort_order": 240,
        "is_active": True,
        "requires_entitlement": False,
        "request_access_url": None,
        "catalog_metadata": {
            "provider": "google",
            "model_id": "gemini-3.1-flash-lite",
            "api_style": "langchain_google_genai",
            "config": {
                "reasoning": {"supported": False, "efforts_available": [], "default_effort": None},
                "sampling": {"temperature": {"default": 0.7, "min": 0.0, "max": 2.0}, "max_output_tokens": {"default": 8192, "max": 8192}},
                "features": {"streaming": True, "vision": True, "tools": True, "json_mode": True},
            },
        },
    },
    {
        "slug": "google-gemini-3-1-flash-lite-preview",
        "display_name": "Gemini 3.1 Flash Lite (preview)",
        "description": (
            "Google Gemini 3.1 Flash Lite preview. "
            "API id ``gemini-3.1-flash-lite-preview``."
        ),
        "api_model_id": "gemini-3.1-flash-lite-preview",
        "effort": "low",
        "sort_order": 250,
        "is_active": True,
        "requires_entitlement": False,
        "request_access_url": None,
        "catalog_metadata": {
            "provider": "google",
            "model_id": "gemini-3.1-flash-lite-preview",
            "api_style": "langchain_google_genai",
            "config": {
                "reasoning": {"supported": False, "efforts_available": [], "default_effort": None},
                "sampling": {"temperature": {"default": 0.7, "min": 0.0, "max": 2.0}, "max_output_tokens": {"default": 8192, "max": 8192}},
                "features": {"streaming": True, "vision": True, "tools": True, "json_mode": True},
            },
        },
    },
    {
        "slug": "google-gemini-3-1-pro",
        "display_name": "Gemini 3.1 Pro",
        "description": (
            "Google Gemini 3.1 Pro — high-capability reasoning model. "
            "API id ``gemini-3.1-pro``."
        ),
        "api_model_id": "gemini-3.1-pro",
        "effort": "high",
        "sort_order": 260,
        "is_active": True,
        "requires_entitlement": False,
        "request_access_url": None,
        "catalog_metadata": {
            "provider": "google",
            "model_id": "gemini-3.1-pro",
            "api_style": "langchain_google_genai",
            "config": {
                "reasoning": {"supported": False, "efforts_available": [], "default_effort": None},
                "sampling": {"temperature": {"default": 0.7, "min": 0.0, "max": 2.0}, "max_output_tokens": {"default": 8192, "max": 65536}},
                "features": {"streaming": True, "vision": True, "tools": True, "json_mode": True},
            },
        },
    },
    {
        "slug": "google-gemini-3-1-pro-preview",
        "display_name": "Gemini 3.1 Pro (preview)",
        "description": (
            "Google Gemini 3.1 Pro preview. "
            "API id ``gemini-3.1-pro-preview``."
        ),
        "api_model_id": "gemini-3.1-pro-preview",
        "effort": "high",
        "sort_order": 270,
        "is_active": True,
        "requires_entitlement": False,
        "request_access_url": None,
        "catalog_metadata": {
            "provider": "google",
            "model_id": "gemini-3.1-pro-preview",
            "api_style": "langchain_google_genai",
            "config": {
                "reasoning": {"supported": False, "efforts_available": [], "default_effort": None},
                "sampling": {"temperature": {"default": 0.7, "min": 0.0, "max": 2.0}, "max_output_tokens": {"default": 8192, "max": 65536}},
                "features": {"streaming": True, "vision": True, "tools": True, "json_mode": True},
            },
        },
    },
]


def upgrade() -> None:
    conn = op.get_bind()

    # Resolve default org id (slug='default')
    org_row = conn.execute(
        sa.text("SELECT id FROM orgs WHERE slug = 'default' LIMIT 1")
    ).fetchone()
    if org_row is None:
        org_row = conn.execute(
            sa.text("SELECT id FROM orgs ORDER BY created_at ASC LIMIT 1")
        ).fetchone()
    org_id = org_row[0] if org_row else None

    # Upsert Gemini models
    for row in _GEMINI_ROWS:
        existing = conn.execute(
            sa.text("SELECT id FROM catalog_models WHERE slug = :slug"),
            {"slug": row["slug"]},
        ).fetchone()

        if existing is None:
            import json
            conn.execute(
                sa.text(
                    """
                    INSERT INTO catalog_models
                        (org_id, slug, display_name, description, api_model_id,
                         effort, sort_order, is_active, requires_entitlement,
                         request_access_url, catalog_metadata)
                    VALUES
                        (:org_id, :slug, :display_name, :description, :api_model_id,
                         :effort, :sort_order, :is_active, :requires_entitlement,
                         :request_access_url, :catalog_metadata::jsonb)
                    """
                ),
                {
                    "org_id": str(org_id) if org_id else None,
                    "slug": row["slug"],
                    "display_name": row["display_name"],
                    "description": row["description"],
                    "api_model_id": row["api_model_id"],
                    "effort": row["effort"],
                    "sort_order": row["sort_order"],
                    "is_active": row["is_active"],
                    "requires_entitlement": row["requires_entitlement"],
                    "request_access_url": row["request_access_url"],
                    "catalog_metadata": json.dumps(row["catalog_metadata"]),
                },
            )

    # Disable all OpenAI models
    conn.execute(
        sa.text("UPDATE catalog_models SET is_active = false WHERE slug LIKE 'openai-%'")
    )


def downgrade() -> None:
    # Remove Gemini rows added by this migration
    slugs = [r["slug"] for r in _GEMINI_ROWS]
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM catalog_models WHERE slug = ANY(:slugs)"),
        {"slugs": slugs},
    )
    # Re-enable OpenAI models (best-effort; original is_active state not stored)
    conn.execute(
        sa.text("UPDATE catalog_models SET is_active = true WHERE slug LIKE 'openai-%'")
    )
