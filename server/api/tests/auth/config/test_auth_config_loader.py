"""Auth-config loader — env-driven strategy enable/disable."""

from __future__ import annotations

import importlib

import pytest

from ai_portal.auth.config import loader as cfg_loader


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in (
        "AUTH_PASSWORD_ENABLED",
        "AUTH_SOCIAL_PROVIDERS",
        "AUTH_DIRECTORY_ENABLED",
        "AUTH_ENTERPRISE_ENABLED",
        "AI_PORTAL_CONFIG",
    ):
        monkeypatch.delenv(k, raising=False)
    # Point at a non-existent config so YAML never bleeds in.
    monkeypatch.setenv("AI_PORTAL_CONFIG", "/nonexistent/auth-config-test.yaml")
    cfg_loader.reset_cache()
    yield
    cfg_loader.reset_cache()


def test_defaults_password_on_enterprise_on_no_social():
    cfg = cfg_loader.get_auth_config()
    assert cfg.password_enabled is True
    assert cfg.enterprise_enabled is True
    assert cfg.directory_enabled is False
    assert cfg.social_providers == ()
    assert cfg.social_enabled is False


def test_password_can_be_disabled(monkeypatch):
    monkeypatch.setenv("AUTH_PASSWORD_ENABLED", "false")
    cfg_loader.reset_cache()
    assert cfg_loader.get_auth_config().password_enabled is False


def test_social_providers_parsed_and_filtered(monkeypatch):
    monkeypatch.setenv("AUTH_SOCIAL_PROVIDERS", "google, github bogus gitlab")
    cfg_loader.reset_cache()
    cfg = cfg_loader.get_auth_config()
    # bogus dropped; known providers preserved in declared order.
    assert cfg.social_providers == ("google", "github", "gitlab")
    assert cfg.social_enabled is True


def test_directory_and_enterprise_toggles(monkeypatch):
    monkeypatch.setenv("AUTH_DIRECTORY_ENABLED", "1")
    monkeypatch.setenv("AUTH_ENTERPRISE_ENABLED", "0")
    cfg_loader.reset_cache()
    cfg = cfg_loader.get_auth_config()
    assert cfg.directory_enabled is True
    assert cfg.enterprise_enabled is False


def test_to_public_dict_shape():
    cfg = cfg_loader.get_auth_config()
    pub = cfg.to_public_dict()
    assert set(pub) == {"password", "social", "directory", "enterprise"}
    assert isinstance(pub["social"], list)
