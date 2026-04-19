"""Tests for catalog/service.py."""
import pytest
from unittest.mock import MagicMock

from ai_portal.catalog.service import (
    effective_chat_model,
    validate_catalog_model_id,
    default_conversation_settings,
)
from ai_portal.core.config import Settings


def test_effective_chat_model_uses_requested():
    settings = MagicMock(spec=Settings)
    settings.chat_default_api_model = "default-model"
    result = effective_chat_model(settings, "claude-3-sonnet")
    assert result == "claude-3-sonnet"


def test_effective_chat_model_falls_back_to_default():
    settings = MagicMock(spec=Settings)
    settings.chat_default_api_model = "default-model"
    result = effective_chat_model(settings, None)
    assert result == "default-model"


def test_effective_chat_model_raises_if_no_model():
    settings = MagicMock(spec=Settings)
    settings.chat_default_api_model = ""
    with pytest.raises(ValueError, match="No chat model configured"):
        effective_chat_model(settings, None)


def test_validate_catalog_model_id_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        validate_catalog_model_id("")


def test_validate_catalog_model_id_optional_id_passes():
    from ai_portal.catalog.definitions import OPTIONAL_CATALOG_API_MODEL_IDS
    if not OPTIONAL_CATALOG_API_MODEL_IDS:
        pytest.skip("No optional IDs defined")
    first = next(iter(OPTIONAL_CATALOG_API_MODEL_IDS))
    validate_catalog_model_id(first)  # Should not raise


def test_default_conversation_settings_returns_object():
    settings = default_conversation_settings()
    assert settings is not None
    assert hasattr(settings, "capabilities")
