# Local E2E (Playwright)

Runs against a **dedicated E2E backend** (port **8001**) and an **isolated Postgres** (port **5435**, database `ai_portal_e2e`). Tests never touch your local-dev database.

---

## Quick start (recommended)

### 1. Start the E2E backend

From the repo root — one command does everything (Docker DB, migrations, catalog seed, uvicorn on 8001):

```bash
./scripts/e2e-up.sh
```

Requires:
- Docker running
- Python venv active: `cd backend && pip install -e ".[dev]"`
- LLM keys in `.env` (only needed for `chat-send.spec.ts`)

### 2. Run Playwright (separate terminal)

```bash
cd frontend
pnpm test:e2e          # headless
pnpm test:e2e:ui       # interactive UI
```

Playwright auto-starts the Vite dev server proxied to port 8001.

First-time browser install: `npx playwright install`

---

## Manual / advanced setup

### Postgres (isolated, port 5435)

```bash
docker compose -f docker-compose.e2e.yml up -d
```

Database URL: `postgresql+psycopg://postgres:postgres@127.0.0.1:5435/ai_portal_e2e`

### Migrations

```bash
cd backend
DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5435/ai_portal_e2e" alembic upgrade head
DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5435/ai_portal_e2e" seed-catalog-models
```

### API on port 8001

```bash
# Windows PowerShell
$env:DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5435/ai_portal_e2e"
$env:API_PORT="8001"
$env:AUTH_MODE="dev"
$env:DEV_BEARER_TOKEN="devtoken"
$env:DEV_SEED_USER_EMAIL="dev@localhost"
$env:UPLOAD_DIR="C:\path\to\ai-portal\.e2e-uploads"
$env:E2E_ENABLE_RAG_SEED="1"    # optional — enables RAG seed endpoint
uvicorn ai_portal.main:app --reload --host 127.0.0.1 --port 8001
```

### Frontend

Playwright's `webServer` block auto-starts Vite with `VITE_DEV_API_PROXY_TARGET=http://127.0.0.1:8001`.
If you want to start it manually:

```bash
cd frontend
VITE_DEV_API_PROXY_TARGET=http://127.0.0.1:8001 pnpm dev
```

Then run Playwright with:

```bash
E2E_BASE_URL=http://localhost:5173 E2E_API_URL=http://127.0.0.1:8001 pnpm test:e2e
```

---

## Environment flags

| Flag | Default | Effect |
|------|---------|--------|
| `E2E_API_URL` | `http://127.0.0.1:8001` | Backend URL used by test helpers and global-setup |
| `E2E_BASE_URL` | *(unset — Playwright starts Vite)* | Set to skip auto-start of the dev server |
| `E2E_CHAT_ENABLED` | *(unset)* | Set to `1` to run `chat-send.spec.ts` (requires live LLM) |
| `E2E_ENABLE_RAG_SEED` | *(unset)* | Set to `1` to enable RAG seed endpoint for KB indicator tests |
| `E2E_REQUIRE_INGEST_READY` | *(unset)* | Set to `1` + working embedding key to assert green "ready" status |
| `E2E_BEARER_TOKEN` | `devtoken` | Bearer token used by test helpers |

---

## Spec overview

| Spec | What it tests | Requires |
|------|---------------|----------|
| `conversation.spec.ts` | Composer, KB picker, attach/detach/search/keyboard, KB indicator | — |
| `chat-parity.spec.ts` | Step 1 spec parity: empty state, starters panel, capabilities menu, model select, no load-older on short thread | — |
| `kb-detail.spec.ts` | KB edit form, save state, upload, delete, empty states | — |
| `kb.spec.ts` | KB list page, create/delete KB | — |
| `chat-kb.spec.ts` | Attach KB via picker, persistence across reload | — |
| `memories.spec.ts` | Memories CRUD, pause/resume, badges | — |
| `chat-send.spec.ts` | Send messages, chat history, model switching | `E2E_CHAT_ENABLED=1` + live LLM |
| `chat-rag-indicator.spec.ts` | KB indicator on assistant messages | `E2E_ENABLE_RAG_SEED=1` |
| `ingest-progress.spec.ts` | Upload → ingest progress tracking | — |
| `rag-toolcall.spec.ts` | RAG tool-call agent loop indicator | `E2E_ENABLE_RAG_SEED=1` |
| `memories-chat.spec.ts` | Homepage cards, memories API visibility | — |

---

## Notes

- Use `waitUntil: 'networkidle'` before clicking UI dependent on React state (TanStack hydration).
- Upload tests wait for `ready` or `failed` status; without an embedding key you'll see `failed` (which is still a passing test).
- All tests run `workers: 1` (serial browser) to avoid port contention on the Vite dev server.
