# YAML Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `.env`-based FastAPI configuration with a structured `backend/config.yaml` file grouped by topic (server, auth, llm, etc.), while keeping env var overrides working for secrets.

**Architecture:** Add a `YamlSettingsSource` to `config.py` that reads `backend/config.yaml`, flattens nested sections into the existing flat `Settings` field names, and plugs into pydantic-settings' source chain at lower priority than env vars. No call sites change.

**Tech Stack:** Python 3.12, pydantic-settings 2.6, pyyaml

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `backend/pyproject.toml` | Add `pyyaml` dependency |
| Modify | `backend/src/ai_portal/config.py` | Add `YamlSettingsSource`, update `Settings` source chain |
| Create | `backend/config.example.yaml` | Committed template with all keys and comments |
| Create | `backend/config.yaml` | Local dev config (gitignored) |
| Modify | `.gitignore` | Add `backend/config.yaml` |
| Modify | `.env.example` | Note that YAML is now primary config |
| Modify | `backend/tests/test_config_validation.py` | Add YAML loading and override tests |

---

### Task 1: Add pyyaml dependency

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add pyyaml to dependencies**

In `backend/pyproject.toml`, add `pyyaml>=6.0` to the `dependencies` list:

```toml
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "pydantic-settings>=2.6",
  "pyyaml>=6.0",
  ...
]
```

- [ ] **Step 2: Install it**

```bash
cd backend
pip install pyyaml>=6.0
```

Expected: installs without error.

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml
git commit -m "chore: add pyyaml dependency"
```

---

### Task 2: Write failing tests for YAML config loading

**Files:**
- Modify: `backend/tests/test_config_validation.py`

- [ ] **Step 1: Add imports and helper at top of test file**

Add after existing imports in `backend/tests/test_config_validation.py`:

```python
import os
import tempfile
from pathlib import Path
```

- [ ] **Step 2: Add YAML loading test**

Append to `backend/tests/test_config_validation.py`:

```python
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
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd backend
pytest tests/test_config_validation.py::test_yaml_values_loaded_into_settings tests/test_config_validation.py::test_env_var_overrides_yaml_secret tests/test_config_validation.py::test_missing_config_yaml_does_not_crash -v
```

Expected: 3 FAILs (Settings doesn't know about YAML yet).

- [ ] **Step 4: Commit failing tests**

```bash
git add backend/tests/test_config_validation.py
git commit -m "test: add failing tests for YAML config loading"
```

---

### Task 3: Implement YamlSettingsSource in config.py

**Files:**
- Modify: `backend/src/ai_portal/config.py`

- [ ] **Step 1: Add imports at top of config.py**

After `from typing import Any, Literal` add:

```python
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
```

Remove the old import line:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict
```

- [ ] **Step 2: Add the YAML key mapping and YamlSettingsSource class**

Insert this block before the `Settings` class definition:

```python
# Maps YAML nested path → flat Settings field name.
# Format: "section.yaml_key": "settings_field_name"
_YAML_KEY_MAP: dict[str, str] = {
    "server.host": "api_host",
    "server.port": "api_port",
    "server.cors_origins": "cors_origins",
    "server.upload_dir": "upload_dir",
    "server.deployment_mode": "deployment_mode",
    "database.url": "database_url",
    "auth.mode": "auth_mode",
    "auth.secret_key": "secret_key",
    "auth.dev_bearer_token": "dev_bearer_token",
    "auth.dev_seed_user_email": "dev_seed_user_email",
    "auth.portal_api_key_pepper": "portal_api_key_pepper",
    "auth.entra_tenant_id": "entra_tenant_id",
    "auth.entra_api_audience": "entra_api_audience",
    "auth.entra_debug_jwt": "entra_debug_jwt",
    "smtp.host": "smtp_host",
    "smtp.port": "smtp_port",
    "smtp.user": "smtp_user",
    "smtp.password": "smtp_password",
    "smtp.email_from": "email_from",
    "llm.openai_api_base": "openai_api_base",
    "llm.openai_api_key": "openai_api_key",
    "llm.anthropic_api_key": "anthropic_api_key",
    "llm.chat_default_api_model": "chat_default_api_model",
    "llm.default_system_prompt": "default_system_prompt",
    "embedding.voyage_api_key": "voyage_api_key",
    "embedding.model": "embedding_model",
    "ingest.max_file_size_mb": "kb_max_file_size_mb",
    "ingest.commit_batch_size": "ingest_commit_batch_size",
    "ingest.embed_batch_size": "ingest_embed_batch_size",
    "rag.max_top_k": "rag_max_top_k",
    "rag.min_top_k": "rag_min_top_k",
    "rag.similarity_threshold": "rag_similarity_threshold",
    "rag.max_tool_iterations": "rag_max_tool_iterations",
    "conversation.base_window_size": "conversation_base_window_size",
    "conversation.summary_interval": "conversation_summary_interval",
    "conversation.inactivity_summary_hours": "conversation_inactivity_summary_hours",
    "observability.langfuse_public_key": "langfuse_public_key",
    "observability.langfuse_secret_key": "langfuse_secret_key",
    "observability.langfuse_host": "langfuse_host",
}


def _default_config_path() -> Path:
    """Return path to config.yaml next to pyproject.toml (i.e. backend/config.yaml)."""
    return Path(__file__).parent.parent.parent.parent / "config.yaml"


class YamlSettingsSource(PydanticBaseSettingsSource):
    """Loads settings from a structured config.yaml, flattening nested sections."""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        env_path = os.environ.get("AI_PORTAL_CONFIG")
        self._path = Path(env_path) if env_path else _default_config_path()

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as fh:
            try:
                data = yaml.safe_load(fh) or {}
            except yaml.YAMLError as exc:
                raise ValueError(f"Invalid YAML in {self._path}: {exc}") from exc
        flat: dict[str, Any] = {}
        for section, values in data.items():
            if not isinstance(values, dict):
                continue
            for key, value in values.items():
                yaml_path = f"{section}.{key}"
                field_name = _YAML_KEY_MAP.get(yaml_path)
                if field_name is not None:
                    flat[field_name] = value
        return flat

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        data = self._load()
        value = data.get(field_name)
        return value, field_name, False

    def __call__(self) -> dict[str, Any]:
        return self._load()
```

- [ ] **Step 3: Update Settings to use YamlSettingsSource and remove env_file**

Replace the `model_config` line and add `settings_customise_sources`:

Change:
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )
```

To:
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        populate_by_name=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        secrets_dir_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (env_settings, YamlSettingsSource(settings_cls), init_settings)
```

- [ ] **Step 4: Run new tests to verify they pass**

```bash
cd backend
pytest tests/test_config_validation.py::test_yaml_values_loaded_into_settings tests/test_config_validation.py::test_env_var_overrides_yaml_secret tests/test_config_validation.py::test_missing_config_yaml_does_not_crash -v
```

Expected: 3 PASSes.

- [ ] **Step 5: Run full test suite to confirm no regressions**

```bash
cd backend
pytest -v
```

Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/config.py
git commit -m "feat: add YamlSettingsSource, load config from structured config.yaml"
```

---

### Task 4: Create config.example.yaml and config.yaml

**Files:**
- Create: `backend/config.example.yaml`
- Create: `backend/config.yaml`

- [ ] **Step 1: Create backend/config.example.yaml**

Create `backend/config.example.yaml` with full contents:

```yaml
# AI Portal configuration
# Copy this file to config.yaml and fill in your values.
# Env vars (e.g. OPENAI_API_KEY) override the values below.

server:
  host: 0.0.0.0
  port: 8000
  cors_origins: http://localhost:5173   # comma-separated for multiple origins
  upload_dir: data/uploads
  deployment_mode: dev                  # dev | saas | selfhosted

database:
  url: postgresql+psycopg://postgres:postgres@127.0.0.1:5434/ai_portal

auth:
  mode: dev                             # dev | entra
  secret_key: ""                        # required for saas/selfhosted; generate with: python -c "import secrets; print(secrets.token_hex(32))"
  dev_bearer_token: devtoken
  dev_seed_user_email: dev@localhost
  portal_api_key_pepper: ""             # required for entra auth; set a long random secret
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
  model: ""                             # e.g. voyage-4-lite or text-embedding-3-small

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

- [ ] **Step 2: Create backend/config.yaml (local dev copy)**

Copy `config.example.yaml` to `config.yaml`:

```bash
cp backend/config.example.yaml backend/config.yaml
```

- [ ] **Step 3: Commit config.example.yaml**

```bash
git add backend/config.example.yaml
git commit -m "feat: add config.example.yaml with all settings grouped by topic"
```

---

### Task 5: Update .gitignore and .env.example

**Files:**
- Modify: `.gitignore`
- Modify: `.env.example`

- [ ] **Step 1: Add backend/config.yaml to .gitignore**

In `.gitignore`, under the `# Env & secrets` section, add:

```
# Env & secrets
.env
.env.local
*.pem
backend/config.yaml
```

- [ ] **Step 2: Update .env.example to reference YAML**

Replace the contents of `.env.example` with:

```
# Primary configuration is now backend/config.yaml
# Copy backend/config.example.yaml → backend/config.yaml for local development.
#
# Env vars below override the corresponding YAML values.
# Use these in Docker / CI / production where you inject secrets via env.

# Secrets (override config.yaml)
SECRET_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
VOYAGE_API_KEY=
DATABASE_URL=

# Frontend (unchanged)
VITE_AUTH_MODE=dev           # dev | local | entra
VITE_API_URL=http://127.0.0.1:8000
VITE_APP_URL=http://localhost:5174
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore .env.example
git commit -m "chore: gitignore backend/config.yaml, update .env.example to reference YAML"
```

---

### Task 6: Final verification

- [ ] **Step 1: Run full test suite**

```bash
cd backend
pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Verify startup uses config.yaml**

Start the backend and confirm it logs values from `config.yaml`:

```bash
cd backend
uvicorn ai_portal.main:app --reload
```

Expected: startup log `app_startup` shows values matching what you put in `config.yaml`.

- [ ] **Step 3: Verify env var override works**

```bash
OPENAI_API_KEY=override-test uvicorn ai_portal.main:app --reload
```

Expected: startup log shows `openai_api_key_set: true` and the value in use is `override-test`, not the one in `config.yaml`.
