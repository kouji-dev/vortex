# YAML Config Design

**Date:** 2026-04-05
**Status:** Approved

## Summary

Replace `.env`-based configuration with a structured `config.yaml` file located at `backend/config.yaml`. Settings are grouped by topic (auth, llm, ingest, etc.). Env vars can still override secrets. The `Settings` model stays flat — no call-site changes needed.

## YAML Structure

```yaml
server:
  host: 0.0.0.0
  port: 8000
  cors_origins: http://localhost:5173
  upload_dir: data/uploads
  deployment_mode: dev   # dev | saas | selfhosted

database:
  url: postgresql+psycopg://postgres:postgres@127.0.0.1:5434/ai_portal

auth:
  mode: dev              # dev | entra
  secret_key: ""
  dev_bearer_token: devtoken
  dev_seed_user_email: dev@localhost
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
```

## Key Mapping (YAML → Settings field)

| YAML path | Settings field |
|---|---|
| `server.host` | `api_host` |
| `server.port` | `api_port` |
| `server.cors_origins` | `cors_origins` |
| `server.upload_dir` | `upload_dir` |
| `server.deployment_mode` | `deployment_mode` |
| `database.url` | `database_url` |
| `auth.mode` | `auth_mode` |
| `auth.secret_key` | `secret_key` |
| `auth.dev_bearer_token` | `dev_bearer_token` |
| `auth.dev_seed_user_email` | `dev_seed_user_email` |
| `auth.portal_api_key_pepper` | `portal_api_key_pepper` |
| `auth.entra_tenant_id` | `entra_tenant_id` |
| `auth.entra_api_audience` | `entra_api_audience` |
| `auth.entra_debug_jwt` | `entra_debug_jwt` |
| `smtp.host` | `smtp_host` |
| `smtp.port` | `smtp_port` |
| `smtp.user` | `smtp_user` |
| `smtp.password` | `smtp_password` |
| `smtp.email_from` | `email_from` |
| `llm.openai_api_base` | `openai_api_base` |
| `llm.openai_api_key` | `openai_api_key` |
| `llm.anthropic_api_key` | `anthropic_api_key` |
| `llm.chat_default_api_model` | `chat_default_api_model` |
| `llm.default_system_prompt` | `default_system_prompt` |
| `embedding.voyage_api_key` | `voyage_api_key` |
| `embedding.model` | `embedding_model` |
| `ingest.max_file_size_mb` | `kb_max_file_size_mb` |
| `ingest.commit_batch_size` | `ingest_commit_batch_size` |
| `ingest.embed_batch_size` | `ingest_embed_batch_size` |
| `rag.max_top_k` | `rag_max_top_k` |
| `rag.min_top_k` | `rag_min_top_k` |
| `rag.similarity_threshold` | `rag_similarity_threshold` |
| `rag.max_tool_iterations` | `rag_max_tool_iterations` |
| `conversation.base_window_size` | `conversation_base_window_size` |
| `conversation.summary_interval` | `conversation_summary_interval` |
| `conversation.inactivity_summary_hours` | `conversation_inactivity_summary_hours` |
| `observability.langfuse_public_key` | `langfuse_public_key` |
| `observability.langfuse_secret_key` | `langfuse_secret_key` |
| `observability.langfuse_host` | `langfuse_host` |

## Architecture

### Source Priority (highest → lowest)
1. Environment variables (for secrets only)
2. `config.yaml`
3. Pydantic field defaults

### Implementation

**`YamlSettingsSource`** — new class in `config.py` implementing `pydantic_settings.PydanticBaseSettingsSource`. Reads `config.yaml` relative to `pyproject.toml` (i.e., `backend/config.yaml`), flattens nested sections using the key mapping table above, returns a flat dict for pydantic to consume.

**`Settings.settings_customise_sources()`** — overrides the default source chain to: `env_settings → yaml_settings → init_settings`. Removes `env_file` from `SettingsConfigDict`.

**Env var overrides for secrets** — pydantic's existing `validation_alias` fields (`SECRET_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DATABASE_URL`, etc.) continue to work unchanged. Env vars take priority over YAML.

**Dependency** — add `pyyaml` to `backend/pyproject.toml`.

### Files Added/Changed
- `backend/config.yaml` — new, gitignored (local config)
- `backend/config.example.yaml` — new, committed (template)
- `backend/src/ai_portal/config.py` — add `YamlSettingsSource`, update `Settings`
- `backend/pyproject.toml` — add `pyyaml` dependency
- `.gitignore` — add `backend/config.yaml`
- `.env.example` — update to note YAML is now primary config

## Error Handling

- If `config.yaml` does not exist, `YamlSettingsSource` returns an empty dict (falls back to env vars and defaults — dev-friendly)
- If `config.yaml` is malformed YAML, raise a clear `ValueError` at startup with the file path

## Testing

- Existing `test_config_validation.py` tests remain valid (pydantic validators unchanged)
- Add test: YAML values are loaded correctly and mapped to flat fields
- Add test: env var overrides YAML value for a secret field
- Add test: missing `config.yaml` does not crash (graceful fallback)
