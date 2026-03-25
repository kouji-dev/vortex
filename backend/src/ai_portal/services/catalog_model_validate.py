"""Lightweight checks for ``catalog_models.api_model_id`` column values."""

from __future__ import annotations

from ai_portal.catalog_model_definitions import OPTIONAL_CATALOG_API_MODEL_IDS


def validate_catalog_model_id(raw: str) -> None:
    s = (raw or "").strip()
    if not s:
        msg = "catalog api_model_id is empty"
        raise ValueError(msg)
    if s in OPTIONAL_CATALOG_API_MODEL_IDS:
        return
    # Non-optional ids: format checks only (no external registry).
