import pytest

from ai_portal.scripts.seed_catalog_models import _CATALOG_SEED_ROWS
from ai_portal.catalog.service import validate_catalog_model_id


@pytest.mark.parametrize(
    "api_model_id",
    [r["api_model_id"] for r in _CATALOG_SEED_ROWS],
    ids=[r["slug"] for r in _CATALOG_SEED_ROWS],
)
def test_catalog_seed_model_ids_validate(api_model_id: str) -> None:
    validate_catalog_model_id(api_model_id)


def test_alembic_baseline_catalog_ids_validate() -> None:
    """Migration 010 inserts these slugs; ids remain valid catalog strings."""
    validate_catalog_model_id("gpt-4o-mini")
    validate_catalog_model_id("gpt-4o")


def test_optional_catalog_ids_allowed() -> None:
    validate_catalog_model_id("gpt-4.5-preview")
    validate_catalog_model_id("gpt-5.4-codex")


def test_empty_catalog_model_id_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        validate_catalog_model_id("")
