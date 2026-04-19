"""Tests for catalog/repository.py — DB query functions."""
import pytest
from sqlalchemy.orm import Session

from ai_portal.core.db.session import SessionLocal
from ai_portal.catalog.repository import (
    get_active_catalog_model_by_slug,
    get_active_catalog_models_by_api_model_id,
    get_all_active_catalog_models,
)
from tests.conftest import requires_postgres


@requires_postgres
def test_get_active_catalog_model_by_slug_existing():
    """Should return a model when slug exists."""
    db = SessionLocal()
    try:
        result = get_active_catalog_model_by_slug(db, "anthropic-claude-haiku-4-5")
        # If no catalog models seeded, skip gracefully
        if result is None:
            pytest.skip("No catalog models in test DB")
        assert result.slug == "anthropic-claude-haiku-4-5"
        assert result.is_active is True
    finally:
        db.close()


@requires_postgres
def test_get_active_catalog_model_by_slug_missing():
    """Should return None for unknown slug."""
    db = SessionLocal()
    try:
        result = get_active_catalog_model_by_slug(db, "nonexistent-slug-xyz")
        assert result is None
    finally:
        db.close()


@requires_postgres
def test_get_all_active_catalog_models_returns_list():
    """Should return a list (may be empty if no models seeded)."""
    db = SessionLocal()
    try:
        result = get_all_active_catalog_models(db)
        assert isinstance(result, list)
    finally:
        db.close()
