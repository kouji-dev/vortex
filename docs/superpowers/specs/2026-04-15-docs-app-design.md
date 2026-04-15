# Vortex Docs App — Design Spec

**Date:** 2026-04-15
**Status:** spec-approved

---

## Overview

A standalone documentation site for Vortex self-hosters — developers and sysadmins deploying Vortex on their own infrastructure. Focus: installation, configuration reference, and operations. Content quality is the primary goal; aesthetics come second.

Separate sub-project at `docs/`, deploying independently. Same pattern as `landing/`.

---

## Goals

- Give self-hosters everything they need to go from zero to running instance
- Document every configurable option with its YAML key, env var alias, default, and description
- Explain non-obvious behaviors (provider fallbacks, first-boot 503 guard, catalog seeding)
- Be the authoritative reference for `config.yaml` — the single source of truth for operators

---

## Tech Stack

| Concern | Choice |
|---|---|
| Framework | [Nextra v3](https://nextra.site) + Next.js 14 |
| Theme | `nextra-theme-docs` with custom Vortex dark theme |
| Styling | CSS variables overriding Nextra defaults — dark background, purple/pink accents |
| Language | TypeScript + MDX |
| Deployment | Static export (`next export`) — Cloudflare Pages / Render static |

**No custom component library.** Nextra's built-in callouts, code blocks, and tables are sufficient.

---

## Project Structure

```
docs/
├── package.json
├── next.config.ts          # Nextra config, static export
├── theme.config.tsx        # Vortex brand — logo, colors, footer, links
├── tsconfig.json
└── pages/
    ├── _app.tsx            # Global CSS overrides
    ├── index.mdx           # Redirects to /getting-started/overview
    ├── _meta.json          # Top-level sidebar ordering
    ├── getting-started/
    │   ├── _meta.json
    │   ├── overview.mdx
    │   ├── prerequisites.mdx
    │   └── quickstart.mdx
    ├── installation/
    │   ├── _meta.json
    │   ├── docker-compose.mdx
    │   └── manual.mdx
    ├── configuration/
    │   ├── _meta.json
    │   ├── overview.mdx
    │   ├── reference.mdx
    │   ├── llm-providers.mdx
    │   ├── embeddings.mdx
    │   ├── auth.mdx
    │   ├── search.mdx
    │   └── fetch.mdx
    └── operations/
        ├── _meta.json
        ├── upgrading.mdx
        ├── backup-restore.mdx
        └── troubleshooting.mdx
```

---

## Site Sections & Content

### Getting Started

**`overview.mdx`**
- What Vortex is: self-hostable AI portal — chat, knowledge bases, model catalog
- Architecture diagram (text-based): Frontend → API → PostgreSQL/pgvector + (optional) Redis
- Key properties: LLM-agnostic, pgvector for RAG, stateless API (Redis optional for future queuing)
- Link to Quickstart

**`prerequisites.mdx`**
- System requirements table:
  - OS: Ubuntu 22.04+ / Debian 12+ (or any Linux distro with Docker support)
  - RAM: 4 GB minimum, 8 GB recommended
  - CPU: 2 cores minimum
  - Disk: 10 GB+ (more if using large knowledge base uploads)
  - Docker: 24.0+ with Compose v2 (for Docker path)
  - Python: 3.12+ (for manual path only)
- External requirements:
  - PostgreSQL 15+ with **pgvector extension** — required for knowledge base / RAG (the `pgvector/pgvector:pg17` Docker image includes this)
  - At least one LLM API key (Anthropic, OpenAI, or Gemini) — Vortex does not bundle a model
  - An embedding provider: Voyage AI API key (recommended) or OpenAI API key — required if using knowledge bases
- Optional:
  - Redis 7+ — not required; ingest runs in-process by default
  - SMTP credentials — required for email verification and password reset in `selfhosted`/`saas` modes

**`quickstart.mdx`**
- Fastest path: Docker Compose
- Steps:
  1. Clone the repo
  2. Create `config.yaml` with minimal required settings (server, database, auth, one LLM key)
  3. `docker compose up -d` (starts Postgres + Redis)
  4. `docker compose --profile full up -d api web` (starts API + frontend)
  5. First-time: navigate to `/setup` to create org + admin account (selfhosted mode) or register (saas mode)
- Annotated minimal `config.yaml` example

---

### Installation

**`docker-compose.mdx`** — Recommended path

1. **Clone**
   ```bash
   git clone https://github.com/your-org/vortex.git
   cd vortex
   ```

2. **Create `config.yaml`** (at repo root, next to `docker-compose.yml`)
   - Minimal required keys: `server.deployment_mode`, `auth.secret_key`, `database.url`, at least one `llm.*_api_key`
   - Full annotated example included

3. **Start infrastructure**
   ```bash
   docker compose up -d
   ```
   Starts Postgres (`pgvector/pgvector:pg17`, port 5434) and Redis (port 6380).

4. **Run migrations** (first time only — auto-runs on every `docker compose` deploy via Dockerfile CMD)
   ```bash
   docker compose --profile full run --rm api alembic upgrade head
   ```

5. **Seed the model catalog**
   ```bash
   docker compose --profile full run --rm api seed-catalog-models
   ```
   Populates `catalog_models` with known Anthropic/OpenAI/Gemini model entries. Required for chat to work.

6. **Start API + frontend**
   ```bash
   docker compose --profile full up -d api web
   ```
   - API: `http://localhost:8000`
   - Frontend: `http://localhost:3000`

7. **First-boot setup** (selfhosted mode only): navigate to `http://localhost:3000/setup`

- Note: `CORS_ORIGINS` must include the frontend URL — default `http://localhost:3000` matches the compose setup.

**`manual.mdx`** — Bare-metal path

Requirements: Python 3.12+, PostgreSQL 15+ with pgvector, Node.js 20+, pnpm.

Backend:
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
alembic upgrade head
seed-catalog-models
uvicorn ai_portal.main:app --host 0.0.0.0 --port 8000
```

Frontend:
```bash
cd frontend
pnpm install
pnpm build && pnpm start   # production
# or:
pnpm dev --host            # development
```

Environment: set `AI_PORTAL_CONFIG=/path/to/config.yaml` or place `config.yaml` in `backend/`.

---

### Configuration

**`overview.mdx`** — How configuration works

Two ways to configure Vortex — both are equivalent; env vars take precedence:

1. **`config.yaml`** — structured YAML file, placed at `backend/config.yaml` by default, or at a custom path via `AI_PORTAL_CONFIG` env var.
2. **Environment variables** — flat `UPPER_CASE` names. Every setting has an env var alias (documented in the reference).

Priority order: `environment variables` > `config.yaml` > `built-in defaults`

Annotated full `config.yaml` skeleton showing all sections with their defaults.

**`reference.mdx`** — Full configuration reference

One table per section. Columns: `yaml key` | `env var` | `default` | `required` | `description`.

Sections and their keys:

**`server`**
| yaml key | env var | default | required | description |
|---|---|---|---|---|
| `server.host` | `API_HOST` | `0.0.0.0` | — | Bind address for the API server |
| `server.port` | `API_PORT` | `8000` | — | TCP port for the API server |
| `server.cors_origins` | `CORS_ORIGINS` | `http://localhost:5173` | yes (prod) | Comma-separated list of allowed frontend origins |
| `server.upload_dir` | `UPLOAD_DIR` | `data/uploads` | — | Directory for uploaded knowledge base files |
| `server.deployment_mode` | `DEPLOYMENT_MODE` | `dev` | yes (prod) | One of `dev`, `saas`, `selfhosted` — see Auth page |

**`database`**
| yaml key | env var | default | required | description |
|---|---|---|---|---|
| `database.url` | `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@127.0.0.1:5434/ai_portal` | yes (prod) | PostgreSQL connection string. Must point to a database with the pgvector extension enabled. |

**`auth`**
| yaml key | env var | default | required | description |
|---|---|---|---|---|
| `auth.mode` | `AUTH_MODE` | `dev` | — | `dev` or `entra`. Legacy field — use `server.deployment_mode` for new deployments. |
| `auth.secret_key` | `SECRET_KEY` | `` | yes in selfhosted/saas | JWT signing secret. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `auth.dev_bearer_token` | `DEV_BEARER_TOKEN` | `devtoken` | — | Fixed bearer token for `dev` mode only. Never use in production. |
| `auth.dev_seed_user_email` | `DEV_SEED_USER_EMAIL` | `dev@localhost` | — | Email for the auto-created dev user. `dev` mode only. |
| `auth.portal_api_key_pepper` | `PORTAL_API_KEY_PEPPER` | `` | yes if AUTH_MODE=entra | HMAC pepper for portal API keys (`aip_…`). Set a long random secret. |
| `auth.entra_tenant_id` | `ENTRA_TENANT_ID` | `` | if AUTH_MODE=entra | Microsoft Entra directory (tenant) UUID. |
| `auth.entra_api_audience` | `ENTRA_API_AUDIENCE` | `` | if AUTH_MODE=entra | Token `aud` claim — e.g. `api://<client-id>` or Application ID URI. |
| `auth.entra_debug_jwt` | `ENTRA_DEBUG_JWT` | `false` | — | Include PyJWT error text in 401 responses. Local debugging only. |

**`smtp`**
| yaml key | env var | default | required | description |
|---|---|---|---|---|
| `smtp.host` | `SMTP_HOST` | `` | yes in selfhosted/saas | SMTP server hostname for email verification and password reset. |
| `smtp.port` | `SMTP_PORT` | `587` | — | SMTP port (587 = STARTTLS, 465 = SSL). |
| `smtp.user` | `SMTP_USER` | `` | — | SMTP authentication username. |
| `smtp.password` | `SMTP_PASSWORD` | `` | — | SMTP authentication password. |
| `smtp.email_from` | `EMAIL_FROM` | `noreply@example.com` | — | From address for outgoing emails. |

**`llm`**
| yaml key | env var | default | required | description |
|---|---|---|---|---|
| `llm.openai_api_key` | `OPENAI_API_KEY` | `` | one LLM key required | API key for OpenAI or any OpenAI-compatible endpoint. |
| `llm.openai_api_base` | `OPENAI_API_BASE` | `https://api.openai.com/v1` | — | Base URL for OpenAI-compatible API. Change to route to a proxy or local model server. |
| `llm.anthropic_api_key` | `ANTHROPIC_API_KEY` | `` | one LLM key required | API key for Anthropic Claude models. |
| `llm.gemini_api_key` | `GEMINI_API_KEY` | `` | one LLM key required | API key for Google Gemini models. |
| `llm.chat_default_api_model` | `CHAT_DEFAULT_API_MODEL` | `gemini-2.5-flash-lite` | — | Default model for new conversations. Accepts vendor API model IDs (e.g. `claude-sonnet-4-6`, `gpt-4o`). Aliases: `CHAT_DEFAULT_MODEL`, `CHAT_MODEL`. |
| `llm.default_system_prompt` | — | `You are a helpful assistant.` | — | Default system prompt for all conversations. |
| `llm.user_search_country` | `USER_SEARCH_COUNTRY` | `FR` | — | ISO country code passed to web search (Anthropic native search, Gemini Google Search). |

**`embedding`**
| yaml key | env var | default | required | description |
|---|---|---|---|---|
| `embedding.voyage_api_key` | `VOYAGE_API_KEY` | `` | yes (if using knowledge bases) | API key for Voyage AI embeddings. Recommended — `voyage-4-lite` has a 200M token/month free tier. |
| `embedding.model` | `EMBEDDING_MODEL` | `` (empty) | — | Embedding model. If empty and `VOYAGE_API_KEY` is set, defaults to `voyage-4-lite`. If empty and using OpenAI, defaults to `text-embedding-3-small`. Override to use a different model. |

**`ingest`**
| yaml key | env var | default | required | description |
|---|---|---|---|---|
| `ingest.max_file_size_mb` | `KB_MAX_FILE_SIZE_MB` | `500` | — | Maximum size of a single knowledge base upload in MB. |
| `ingest.commit_batch_size` | `INGEST_COMMIT_BATCH_SIZE` | `100` | — | Number of chunks committed per DB transaction during ingest. |
| `ingest.embed_batch_size` | `INGEST_EMBED_BATCH_SIZE` | `128` | — | Number of chunks sent to the embedding API per request. |

**`rag`**
| yaml key | env var | default | required | description |
|---|---|---|---|---|
| `rag.max_top_k` | `RAG_MAX_TOP_K` | `30` | — | Maximum number of chunks retrieved per RAG query. |
| `rag.min_top_k` | `RAG_MIN_TOP_K` | `8` | — | Minimum chunks retrieved even if similarity threshold filters more. |
| `rag.similarity_threshold` | `RAG_SIMILARITY_THRESHOLD` | `0.3` | — | Cosine similarity cutoff. Chunks below this score are discarded. |
| `rag.max_tool_iterations` | `RAG_MAX_TOOL_ITERATIONS` | `1` | — | Maximum RAG tool call iterations per chat turn. |

**`conversation`**
| yaml key | env var | default | required | description |
|---|---|---|---|---|
| `conversation.base_window_size` | `CONVERSATION_BASE_WINDOW_SIZE` | `30` | — | Number of messages kept in context before summarization. Alias: `CONVERSATION_WINDOW_SIZE`. |
| `conversation.summary_interval` | `CONVERSATION_SUMMARY_INTERVAL` | `10` | — | Summarize the conversation every N new messages. |
| `conversation.inactivity_summary_hours` | `CONVERSATION_INACTIVITY_SUMMARY_HOURS` | `1` | — | Trigger a summary after this many hours of inactivity. |

**`observability`**
| yaml key | env var | default | required | description |
|---|---|---|---|---|
| `observability.langfuse_public_key` | — | `` | — | Langfuse public key for LLM observability tracing. Optional. |
| `observability.langfuse_secret_key` | — | `` | — | Langfuse secret key. |
| `observability.langfuse_host` | — | `https://cloud.langfuse.com` | — | Langfuse server URL. Override for self-hosted Langfuse. |

**`search`**
| yaml key | env var | default | required | description |
|---|---|---|---|---|
| `search.provider` | `SEARCH_PROVIDER` | `duckduckgo` | — | Web search provider for the `web_search` tool. Options: `duckduckgo`, `tavily`, `serper`, `exa`. Falls back to DuckDuckGo if the configured provider's API key is missing. |
| `search.tavily_api_key` | `TAVILY_API_KEY` | `` | if provider=tavily | API key for Tavily search. |
| `search.serper_api_key` | `SERPER_API_KEY` | `` | if provider=serper | API key for Serper (Google Search API). |
| `search.exa_api_key` | `EXA_API_KEY` | `` | if provider=exa | API key for Exa semantic search. |

**`fetch`**
| yaml key | env var | default | required | description |
|---|---|---|---|---|
| `fetch.firecrawl_api_key` | `FIRECRAWL_API_KEY` | `` | — | API key for Firecrawl. When set, Firecrawl is used first in the fetch chain (best Cloudflare/bot-protection bypass). |
| `fetch.jina_api_key` | `JINA_API_KEY` | `` | — | Jina Reader API key. Jina is always in the chain (free, no key required); setting a key increases rate limits. |

**`llm-providers.mdx`** — LLM Providers

Three supported providers. At least one API key must be set.

**Anthropic (Claude)**
- Set `llm.anthropic_api_key` (`ANTHROPIC_API_KEY`)
- Supported models: `claude-sonnet-4-6`, `claude-opus-4-6`, `claude-haiku-4-5-20251001`, and others from the model catalog
- Claude models support extended thinking and native tool use
- Note: Anthropic API keys do not provide embeddings — set `VOYAGE_API_KEY` or `OPENAI_API_KEY` separately for knowledge base functionality

**OpenAI / OpenAI-compatible**
- Set `llm.openai_api_key` (`OPENAI_API_KEY`)
- Default base URL: `https://api.openai.com/v1`
- To use a compatible gateway (Azure OpenAI, LM Studio, Ollama, etc.): set `llm.openai_api_base` to the endpoint URL
- OpenAI keys also power embeddings when `VOYAGE_API_KEY` is not set

**Google Gemini**
- Set `llm.gemini_api_key` (`GEMINI_API_KEY`)
- Supported models: `gemini-2.5-flash`, `gemini-2.5-flash-lite`, etc.
- Default model (`gemini-2.5-flash-lite`) is the lowest-cost option

**Using multiple providers**
- You can set multiple API keys — the model catalog determines which model uses which provider
- The `chat_default_api_model` sets the fallback model for new conversations if no catalog default is configured

**`embeddings.mdx`** — Embeddings

Embeddings are required for knowledge base and RAG functionality. Two options:

**Option A — Voyage AI (recommended)**
- Set `VOYAGE_API_KEY`
- Default model: `voyage-4-lite` — lowest-cost Voyage text embedding tier, 200M tokens/month free
- Vectors stored as `vector(1024)` in pgvector
- No `EMBEDDING_MODEL` needed unless switching to a different Voyage model

**Option B — OpenAI-compatible**
- No `VOYAGE_API_KEY` — Vortex falls back to `OpenAIEmbeddings` using `OPENAI_API_KEY`
- Default model: `text-embedding-3-small` (with `dimensions=1024` to match pgvector column)
- Set `EMBEDDING_MODEL` to override the model name
- Compatible with any OpenAI-compatible embedding endpoint via `OPENAI_API_BASE`

> Warning: Do not mix embedding providers after documents have been ingested — vectors from different models are not comparable. If you switch providers, re-ingest all knowledge base documents.

**`auth.mdx`** — Auth & Deployment Modes

Three deployment modes controlled by `DEPLOYMENT_MODE`:

**`dev`** (default — local development only)
- All routes accept a fixed bearer token (`DEV_BEARER_TOKEN`, default `devtoken`)
- A seed user (`DEV_SEED_USER_EMAIL`) is auto-created on startup
- No `SECRET_KEY` required
- Never use in production — no authentication security

**`selfhosted`** (single-organization, invite-only)
- Requires `SECRET_KEY` (JWT signing)
- On first boot with no organizations in the database: all routes return `503 Setup Required` except `/health`, `/setup`, and `/auth/login`
- Navigate to `/setup` in the frontend to create the instance org and admin account
- After setup, invite users from the admin panel
- SMTP required for email verification and password reset

**`saas`** (open signup, multi-tenant)
- Requires `SECRET_KEY`
- Open registration via `/auth/register`
- SMTP required for email verification

**First-boot flow (`selfhosted` mode)**

```
Deploy with DEPLOYMENT_MODE=selfhosted
        ↓
All API routes → 503 (except /health, /setup, /auth/login)
        ↓
Navigate to https://your-app/setup
        ↓
POST /setup { org_name, admin_email, admin_password }
        ↓
Instance live — log in with admin credentials
```

**Microsoft Entra (legacy)**
- `AUTH_MODE=entra` — validates Microsoft Entra JWTs
- Requires `ENTRA_TENANT_ID` and `ENTRA_API_AUDIENCE`
- `PORTAL_API_KEY_PEPPER` is required when `AUTH_MODE=entra`
- Frontend: set `VITE_AUTH_MODE=entra`, `VITE_ENTRA_SPA_CLIENT_ID`, `VITE_ENTRA_TENANT_ID`, `VITE_ENTRA_API_SCOPE`

**`search.mdx`** — Search Providers

The `web_search` tool uses a configurable search provider. Set `search.provider` to one of:

| Provider | Key required | Notes |
|---|---|---|
| `duckduckgo` | No | Default. No key needed, rate-limited. |
| `tavily` | `TAVILY_API_KEY` | Best quality for AI applications. |
| `serper` | `SERPER_API_KEY` | Google Search via Serper API. |
| `exa` | `EXA_API_KEY` | Semantic / neural search. |

**Fallback behavior:** If a provider is configured but its API key is missing, Vortex falls back to DuckDuckGo automatically and logs a warning.

**`fetch.mdx`** — Fetch Providers

The `fetch_webpage` tool uses a chain of providers. Vortex tries each in order and returns the first success:

| Priority | Provider | Key required | Notes |
|---|---|---|---|
| 1 | Firecrawl | `FIRECRAWL_API_KEY` | Best Cloudflare/bot-protection bypass. Only active if key is set. |
| 2 | Crawl4AI | None | Local Playwright + stealth mode. Active if the `crawl4ai` Python package is installed. |
| 3 | Jina Reader | Optional (`JINA_API_KEY`) | `r.jina.ai` proxy. Always active. Key increases rate limits. |
| 4 | requests | None | Plain HTTP fallback. Always active. Fails on JS-heavy or bot-protected pages. |

No configuration is needed beyond setting the optional API keys. Vortex builds the chain automatically based on what's available.

---

### Operations

**`upgrading.mdx`**
- Pull the latest code
- Rebuild Docker images: `docker compose --profile full build`
- Migrations run automatically on container start (Dockerfile CMD: `alembic upgrade head && uvicorn …`)
- Re-run `seed-catalog-models` if the changelog mentions new model catalog entries
- No data migration needed for config.yaml changes

**`backup-restore.mdx`**
- Backup: `pg_dump` the database + copy `UPLOAD_DIR` (knowledge base files)
- Docker volume backup: `docker compose down`, copy `ai-portal-db-data` volume
- Restore: `pg_restore` + copy uploads back, `docker compose up -d`
- Knowledge base vectors are stored in the DB — no separate vector store to back up

**`troubleshooting.mdx`**
- `503 Setup Required` on all routes → `DEPLOYMENT_MODE=selfhosted` and no orgs created yet → go to `/setup`
- Chat returns no response → no LLM API key set, or `CHAT_DEFAULT_API_MODEL` points to a model whose key is missing
- Knowledge base upload fails → embedding provider not configured (neither `VOYAGE_API_KEY` nor `OPENAI_API_KEY` set)
- CORS errors → `CORS_ORIGINS` does not include the frontend URL
- Migration errors on start → database not reachable, or pgvector extension not installed
- `SECRET_KEY must be set` error → deployment mode is `saas`/`selfhosted` but `SECRET_KEY` is empty

---

## Branding & Theme

Nextra theming via `theme.config.tsx` and CSS variable overrides in `_app.tsx`:

- Background: `#0f0f17` (matches landing page)
- Sidebar accent: `#7c3aed` (Vortex purple)
- Active link: `#a78bfa`
- Code block background: `#1e1b2e`
- Callout accent: purple (info), amber (warning), red (danger)
- Font: system-ui (same as landing)
- Logo: Vortex wordmark / PrismLogo from landing assets (SVG import)

---

## Deployment

- `next build && next export` → static `out/` directory
- Add to `render.yaml` as a new static site service:
  ```yaml
  - type: web
    name: ai-portal-docs
    runtime: node
    rootDir: docs
    buildCommand: npm install -g pnpm && pnpm install && pnpm run build
    startCommand: pnpm run start
    plan: starter
  ```
- Or deploy to Cloudflare Pages (zero config, static export)

---

## Out of Scope (v1)

- API reference (OpenAPI / Swagger)
- Versioned docs (multiple Vortex release branches)
- Search (Nextra built-in Algolia DocSearch — future enhancement)
- Contributing guide
- Localization
