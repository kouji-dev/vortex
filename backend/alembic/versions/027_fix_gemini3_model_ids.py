"""Fix Gemini 3 api_model_ids: add -preview suffix to match actual Google API IDs.

Revision ID: 027_fix_gemini3_model_ids
Revises: 026_gemini_models_disable_openai
Create Date: 2026-04-08

Migration 026 added Gemini 3.x models with speculative api_model_ids that
lacked the -preview suffix required by the real Google API.

Fixes:
  gemini-3-flash          → gemini-3-flash-preview
  gemini-3.1-flash-lite   → gemini-3.1-flash-lite-preview
  gemini-3.1-pro          → gemini-3.1-pro-preview

Models already correct (gemini-3.1-flash-lite-preview, gemini-3.1-pro-preview)
are left untouched.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "027_fix_gemini3_model_ids"
down_revision = "026_gemini_models_disable_openai"
branch_labels = None
depends_on = None

_FIXES = [
    ("google-gemini-3-flash", "gemini-3-flash-preview"),
    ("google-gemini-3-1-flash-lite", "gemini-3.1-flash-lite-preview"),
    ("google-gemini-3-1-pro", "gemini-3.1-pro-preview"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for slug, new_api_model_id in _FIXES:
        conn.execute(
            sa.text(
                "UPDATE catalog_models SET api_model_id = :api_model_id WHERE slug = :slug"
            ),
            {"api_model_id": new_api_model_id, "slug": slug},
        )


def downgrade() -> None:
    conn = op.get_bind()
    _originals = [
        ("google-gemini-3-flash", "gemini-3-flash"),
        ("google-gemini-3-1-flash-lite", "gemini-3.1-flash-lite"),
        ("google-gemini-3-1-pro", "gemini-3.1-pro"),
    ]
    for slug, original_api_model_id in _originals:
        conn.execute(
            sa.text(
                "UPDATE catalog_models SET api_model_id = :api_model_id WHERE slug = :slug"
            ),
            {"api_model_id": original_api_model_id, "slug": slug},
        )
