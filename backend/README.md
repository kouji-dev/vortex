# AI Portal API

## LLM & embeddings (architecture)

Production **chat** and **embedding** calls use **LangChain** in-process: `services/llm_providers/langchain_chat.py` (`ChatAnthropic` / `ChatOpenAI`) and `services/embedding.py` (`OpenAIEmbeddings`). Point `LLM_API_BASE` at any OpenAI-compatible endpoint when needed (direct vendor or a self-hosted gateway).

**Azure accounts:** Microsoft’s [free Azure services](https://azure.microsoft.com/pricing/free-services) list includes **many** AI products (Vision, Translator, Speech, Language, etc.) with monthly free allowances, but **Azure OpenAI / Foundry generative chat models are metered—you pay per token** (or spend time-limited **account credits**, where offered). They are **not** the same as those fixed “always free” AI SKUs. Eligibility and any **limited-access** rules follow [Microsoft’s current policies](https://learn.microsoft.com/azure/ai-foundry/responsible-ai/openai/limited-access). For simple local dev, **OpenAI** or **Anthropic** API keys are often easier than standing up Azure OpenAI.

**Model catalog metadata** (product-visible catalog fields, access configuration, etc.) is specified to live in **PostgreSQL and documented HTTP APIs** (REQ-META). See [`docs/superpowers/specs/2026-03-22-model-platform-requirements.md`](../docs/superpowers/specs/2026-03-22-model-platform-requirements.md).

## Run (dev)

From repo root, with Postgres up (`docker compose up -d`):

```bash
cd backend
pip install -e ".[dev]"
uvicorn ai_portal.main:app --reload --host 0.0.0.0 --port 8000
```

Env: copy repo root `.env.example` to `.env`. Important keys: `DATABASE_URL`, `DEV_BEARER_TOKEN`, `DEV_SEED_USER_EMAIL`, `LLM_API_KEY` (or `OPENAI_API_KEY` alias) for OpenAI-compatible chat + embeddings, `ANTHROPIC_API_KEY` for Claude catalog models, `UPLOAD_DIR`, optional `PORTAL_API_KEY_PEPPER` for hashed `aip_…` API keys.

### Microsoft Entra (production-style API auth)

Design: [`docs/superpowers/specs/2026-03-22-auth-entra-design.md`](../docs/superpowers/specs/2026-03-22-auth-entra-design.md).

| Variable | Purpose |
|----------|---------|
| `AUTH_MODE` | `dev` (default): bearer `DEV_BEARER_TOKEN` → seed user. `entra`: validate JWTs for this API. |
| `ENTRA_TENANT_ID` | Entra tenant UUID (directory). |
| `ENTRA_API_AUDIENCE` | Access token `aud` — e.g. `api://<api-app-client-id>` or Application ID URI. |

**App registrations (summary):** SPA: auth code + PKCE, redirect to dev/prod origin. API: expose delegated scope; define app roles if using RBAC. Grant SPA permission to API scope; admin consent.

**Frontend (Vite):** `VITE_AUTH_MODE=entra`, `VITE_ENTRA_SPA_CLIENT_ID`, `VITE_ENTRA_TENANT_ID`, `VITE_ENTRA_API_SCOPE` (full scope string). In `dev` mode the UI sends `VITE_DEV_BEARER_TOKEN` (default `devtoken`).

## Tests

Postgres must be reachable at `DATABASE_URL` for integration tests (`test_chat_roundtrip`, model smoke, etc.). CI runs `alembic upgrade head` then `pytest`.

```bash
cd backend
pytest tests -v
```

## Migrations

Order: `001` (vector extension) → `002_core_catalog` → `003_chat` → `004_rag` → `005_entra_oid` → `006_drop_roles` (removed local `roles` / `user_roles`; app RBAC uses Entra JWT `roles` when `AUTH_MODE=entra`). Later revisions add portal API keys, chat JSON checks, and `010`/`011` catalog tables + structured `catalog_metadata.config`.

If you upgraded from an older clone whose `catalog_models` table still has a **legacy** vendor-model column name, align it with the ORM by renaming that column to **`api_model_id`** in PostgreSQL (inspect `\d catalog_models` first), then continue with `alembic upgrade head`.

```bash
cd backend
alembic upgrade head
```

### After a database reset (new or wiped Postgres volume)

From repo root, bring Postgres up, then apply schema and **sync catalog rows** from the seed script (same order CI uses):

```bash
docker compose up -d
cd backend
# DATABASE_URL must match your compose port (see repo root .env.example, e.g. 127.0.0.1:5434)
alembic upgrade head
seed-catalog-models
# To skip catalog id validation (offline / custom forks):
# seed-catalog-models --skip-model-validation
```

A reset typically means `docker compose down -v` (removes volumes) before `up -d`.

### Seed catalog rows (Azure OpenAI + Anthropic)

After migrations, upsert catalog rows into ``catalog_models`` (OpenAI-style ids and Anthropic ``claude-…`` ids; column ``api_model_id``):

```bash
cd backend
pip install -e .
seed-catalog-models
# preview: seed-catalog-models --dry-run
```

Edit ``src/ai_portal/catalog_model_definitions.py`` (slug ↔ API model id, entitlements) and ``src/ai_portal/catalog_specs.py`` (per-model ``config``: reasoning, sampling, features). The seed script upserts those rows and deactivates legacy slugs. For Anthropic, set ``ANTHROPIC_API_KEY``; for OpenAI routes, set ``LLM_API_KEY`` and ``LLM_API_BASE``. After seeding, new chats default to **Claude Haiku 4.5** via catalog slug ``anthropic-claude-haiku-4-5``; set ``CHAT_DEFAULT_API_MODEL`` / ``CHAT_DEFAULT_MODEL`` if that row is absent. Set ``CHAT_MODEL`` to a row’s ``api_model_id`` for stream fallback when no per-request model is set.
