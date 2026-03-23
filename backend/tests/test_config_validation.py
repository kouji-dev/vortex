import pytest
from pydantic import ValidationError

from ai_portal.config import Settings, validate_portal_api_key_pepper_for_auth_mode


def test_validate_portal_api_key_pepper_entra_requires_non_empty():
    with pytest.raises(ValueError, match="PORTAL_API_KEY_PEPPER"):
        validate_portal_api_key_pepper_for_auth_mode("entra", "")
    with pytest.raises(ValueError, match="PORTAL_API_KEY_PEPPER"):
        validate_portal_api_key_pepper_for_auth_mode("entra", "   ")


def test_validate_portal_api_key_pepper_dev_allows_empty():
    validate_portal_api_key_pepper_for_auth_mode("dev", "")
    validate_portal_api_key_pepper_for_auth_mode("dev", "  ")


def test_settings_entra_rejects_blank_pepper(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "entra")
    monkeypatch.setenv("PORTAL_API_KEY_PEPPER", "")
    monkeypatch.setenv("ENTRA_TENANT_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("ENTRA_API_AUDIENCE", "api://x")
    with pytest.raises(ValidationError, match="PORTAL_API_KEY_PEPPER"):
        Settings()


def test_settings_entra_accepts_pepper(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "entra")
    monkeypatch.setenv("PORTAL_API_KEY_PEPPER", "not-empty")
    monkeypatch.setenv("ENTRA_TENANT_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("ENTRA_API_AUDIENCE", "api://x")
    s = Settings()
    assert s.portal_api_key_pepper == "not-empty"
