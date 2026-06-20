import os
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_portal.core.config import Settings


def test_default_deployment_mode_is_saas(monkeypatch):
    """Default deployment_mode is 'saas'."""
    # Ensure DEPLOYMENT_MODE is not set from env
    monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)
    # secret_key required for saas; provide it
    monkeypatch.setenv("SECRET_KEY", "a" * 32)
    s = Settings()
    assert s.deployment_mode == "saas"


def test_secret_key_required_for_saas(monkeypatch):
    """SECRET_KEY must be set for deployment_mode=saas."""
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("SECRET_KEY", "")
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings()


def test_secret_key_required_for_selfhosted(monkeypatch):
    """SECRET_KEY must be set for deployment_mode=selfhosted."""
    monkeypatch.setenv("DEPLOYMENT_MODE", "selfhosted")
    monkeypatch.setenv("SECRET_KEY", "")
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings()


def test_saas_with_secret_key_ok(monkeypatch):
    """saas mode with a valid secret_key loads without error."""
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("SECRET_KEY", "s" * 32)
    s = Settings()
    assert s.deployment_mode == "saas"
    assert s.secret_key == "s" * 32


def test_yaml_values_loaded_into_settings(monkeypatch, tmp_path):
    """Values from config.yaml are mapped to flat Settings fields."""
    yaml_content = """
server:
  host: 1.2.3.4
  port: 9999
  cors_origins: http://example.com
  upload_dir: data/test
  deployment_mode: saas
database:
  url: postgresql+psycopg://user:pass@localhost/testdb
auth:
  secret_key: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
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
    for key in ["API_HOST", "API_PORT", "DATABASE_URL", "SECRET_KEY", "DEPLOYMENT_MODE"]:
        monkeypatch.delenv(key, raising=False)

    s = Settings()

    assert s.api_host == "1.2.3.4"
    assert s.api_port == 9999
    assert s.cors_origins == "http://example.com"
    assert s.database_url == "postgresql+psycopg://user:pass@localhost/testdb"
    assert s.deployment_mode == "saas"


def test_env_var_overrides_yaml_secret(monkeypatch, tmp_path):
    """Env vars take priority over YAML for secret fields."""
    yaml_content = """
llm:
  openai_api_key: from-yaml
auth:
  secret_key: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  portal_api_key_pepper: ""
  entra_tenant_id: ""
  entra_api_audience: ""
  entra_debug_jwt: false
server:
  host: 0.0.0.0
  port: 8000
  cors_origins: http://localhost:5173
  upload_dir: data/uploads
  deployment_mode: saas
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
    monkeypatch.setenv("SECRET_KEY", "b" * 32)
    # Should not raise
    s = Settings()
    assert s.api_port == 8000  # pydantic default
