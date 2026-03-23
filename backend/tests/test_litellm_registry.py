import pytest

from ai_portal.scripts.seed_catalog_models import _CATALOG_SEED_ROWS
from ai_portal.services.litellm_registry import (
    completion_model_id_for_catalog_row,
    validate_catalog_litellm_model_id,
)


@pytest.mark.parametrize(
    "litellm_model_id",
    [r["litellm_model_id"] for r in _CATALOG_SEED_ROWS],
    ids=[r["slug"] for r in _CATALOG_SEED_ROWS],
)
def test_catalog_seed_litellm_ids_are_registered(litellm_model_id: str) -> None:
    validate_catalog_litellm_model_id(litellm_model_id)


def test_alembic_baseline_catalog_ids_are_registered() -> None:
    """Migration 010 inserts these slugs; keep their ``litellm_model_id`` in LiteLLM."""
    validate_catalog_litellm_model_id("gpt-4o-mini")
    validate_catalog_litellm_model_id("gpt-4o")


def test_optional_catalog_ids_skip_litellm_registry() -> None:
    validate_catalog_litellm_model_id("gpt-4.5-preview")
    validate_catalog_litellm_model_id("gpt-5.4-codex")


def test_completion_id_applies_anthropic_prefix_for_claude() -> None:
    assert completion_model_id_for_catalog_row("claude-haiku-4-5") == (
        "anthropic/claude-haiku-4-5"
    )
