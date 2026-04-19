import os
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_portal.core.config import Settings, validate_portal_api_key_pepper_for_auth_mode


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


def test_yaml_values_loaded_into_settings(monkeypatch, tmp_path):
    """Values from config.yaml are mapped to flat Settings fields."""
    yaml_content = """
server:
  host: 1.2.3.4
  port: 9999
  cors_origins: http://example.com
  upload_dir: data/test
  deployment_mode: dev
database:
  url: postgresql+psycopg://user:pass@localhost/testdb
auth:
  mode: dev
  secret_key: ""
  dev_bearer_token: testtoken
  dev_seed_user_email: test@test.com
  portal_api_key_pepper: ""
  entra_tenant_id: ""
  entra_api_audience: ""
  entra_debug_jwt: false
smtp:
  host: ""
  port: 587
  user: ""
  password: ""
  email_from: noreply@example.com
llm:
  openai_api_base: https://api.openai.com/v1
  openai_api_key: ""
  anthropic_api_key: ""
  chat_default_api_model: claude-haiku-4-5-20251001
  default_system_prompt: "You are a helpful assistant."
embedding:
  voyage_api_key: ""
  model: ""
ingest:
  max_file_size_mb: 500
  commit_batch_size: 100
  embed_batch_size: 128
rag:
  max_top_k: 30
  min_top_k: 8
  similarity_threshold: 0.3
  max_tool_iterations: 1
conversation:
  base_window_size: 30
  summary_interval: 10
  inactivity_summary_hours: 1
observability:
  langfuse_public_key: ""
  langfuse_secret_key: ""
  langfuse_host: https://cloud.langfuse.com
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml_content)
    monkeypatch.setenv("AI_PORTAL_CONFIG", str(config_file))
    # Clear any leftover env vars that might shadow YAML values
    for key in ["API_HOST", "API_PORT", "DATABASE_URL"]:
        monkeypatch.delenv(key, raising=False)

    s = Settings()

    assert s.api_host == "1.2.3.4"
    assert s.api_port == 9999
    assert s.cors_origins == "http://example.com"
    assert s.database_url == "postgresql+psycopg://user:pass@localhost/testdb"
    assert s.dev_bearer_token == "testtoken"


def test_env_var_overrides_yaml_secret(monkeypatch, tmp_path):
    """Env vars take priority over YAML for secret fields."""
    yaml_content = """
llm:
  openai_api_key: from-yaml
auth:
  secret_key: yaml-secret
  mode: dev
  dev_bearer_token: devtoken
  dev_seed_user_email: dev@localhost
  portal_api_key_pepper: ""
  entra_tenant_id: ""
  entra_api_audience: ""
  entra_debug_jwt: false
server:
  host: 0.0.0.0
  port: 8000
  cors_origins: http://localhost:5173
  upload_dir: data/uploads
  deployment_mode: dev
database:
  url: postgresql+psycopg://postgres:postgres@127.0.0.1:5434/ai_portal
smtp:
  host: ""
  port: 587
  user: ""
  password: ""
  email_from: noreply@example.com
embedding:
  voyage_api_key: ""
  model: ""
ingest:
  max_file_size_mb: 500
  commit_batch_size: 100
  embed_batch_size: 128
rag:
  max_top_k: 30
  min_top_k: 8
  similarity_threshold: 0.3
  max_tool_iterations: 1
conversation:
  base_window_size: 30
  summary_interval: 10
  inactivity_summary_hours: 1
observability:
  langfuse_public_key: ""
  langfuse_secret_key: ""
  langfuse_host: https://cloud.langfuse.com
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml_content)
    monkeypatch.setenv("AI_PORTAL_CONFIG", str(config_file))
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")

    s = Settings()

    assert s.openai_api_key == "from-env"


def test_missing_config_yaml_does_not_crash(monkeypatch, tmp_path):
    """If config.yaml does not exist, Settings loads from defaults/env without error."""
    monkeypatch.setenv("AI_PORTAL_CONFIG", str(tmp_path / "nonexistent.yaml"))
    # Should not raise
    s = Settings()
    assert s.api_port == 8000  # pydantic default
