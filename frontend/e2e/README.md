# Local E2E (Playwright)

Runs against a **dedicated E2E backend** (port **8001**) and an **isolated Postgres** (port **5435**, database `ai_portal_e2e`). Tests never touch your local-dev database.

This layout matches `docs/superpowers/specs/2026-04-04-e2e-refactor-design.md`: specs are grouped by **topic** under `shell/`, `chat/`, `kb/`, and `memories/`, with shared code in `support/` and KB UI flows in `kb/helpers.ts`.

---

## Quick start

### Option A — from this worktree root (Linux / macOS / Git Bash)

Starts Docker, migrations, seed, API **8001**, then Playwright (Vite **5174**):

```bash
pnpm test:e2e:all
```

If the stack is **already** running:

```bash
SKIP_E2E_STACK=1 pnpm test:e2e:all
```

### Option B — Windows PowerShell

Terminal 1 (Git Bash recommended): `./scripts/e2e-up.sh`  
Terminal 2:

```powershell
pnpm test:e2e:win
```

Or from `frontend/` only:

```bash
cd frontend
pnpm test:e2e
```

Playwright auto-starts the Vite dev server proxied to port **8001**.

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

See `scripts/e2e-up.sh` for the full env (`E2E_ENABLE_CHAT_MESSAGES_SEED`, `E2E_ENABLE_RAG_SEED`, `KB_MAX_FILE_SIZE_MB=1`, etc.).

### Frontend

Playwright `webServer` starts Vite on **5174** with `VITE_DEV_API_PROXY_TARGET` pointing at **8001**.

---

## Environment (Playwright only)

| Variable | Default | Effect |
|----------|---------|--------|
| `E2E_API_URL` | `http://127.0.0.1:8001` | Backend URL for helpers + global-setup |
| `E2E_BASE_URL` | *(unset — Playwright starts Vite)* | Use a running dev server instead of auto-start |
| `E2E_BEARER_TOKEN` | `devtoken` | Dev bearer for API helpers |

---

## Spec layout

| Folder | Spec | What it tests | Requires |
|--------|------|---------------|----------|
| `shell/` | `conversations-sidebar.spec.ts` | Sidebar selection mode, bulk/single delete dialogs | — |
| `shell/` | `chat-parity.spec.ts` | Empty state, starters, capabilities menu, load-older seed | `e2e-up.sh` (`E2E_ENABLE_CHAT_MESSAGES_SEED`) |
| `shell/` | `memories-chat.spec.ts` | Home → Memories link, API create/delete | — |
| `chat/` | `conversation.spec.ts` | Composer, KB picker, indicator popover, thread delete | RAG seed for seeded-message tests |
| `chat/` | `chat-send.spec.ts` | Send/stream, model select, sidebar after message | **Anthropic** (Haiku) |
| `chat/` | `chat-kb.spec.ts` | Create KB + attach via picker, reload persistence | — |
| `chat/` | `chat-rag-indicator.spec.ts` | KB control on seeded assistant message | RAG seed |
| `chat/` | `rag-toolcall.spec.ts` | Seeded tool-call UI + live stream line | RAG seed + **Anthropic** |
| `chat/` | `chat-attachments.spec.ts` | Upload API, stream `attachment_ids`, file in answer | Migration + **Anthropic** |
| `kb/` | `kb-list.spec.ts` | List table, search, create via dialog | — |
| `kb/` | `kb-detail.spec.ts` | Detail form, upload row, delete doc, empty state | Embeddings for row visibility timing |
| `kb/` | `ingest-progress.spec.ts` | Ingest → **ready**; oversize rejection | Embeddings; `KB_MAX_FILE_SIZE_MB=1` |
| `memories/` | `memories.spec.ts` | Memories CRUD, pause/resume, delete dialogs | — |

**Removed (redundant):** `kb.spec.ts` duplicated the ingest-to-ready journey now covered by `kb/ingest-progress.spec.ts`. **Green “ready” styling** on the detail page is intentionally only asserted in `ingest-progress` to avoid two long embeddings-backed tests.

---

## Notes

- Shared helpers: `support/*.ts`, topic UI: `kb/helpers.ts` (importable from other folders when needed).
- Use `waitUntil: 'networkidle'` before clicking UI dependent on React state (TanStack hydration).
- `playwright.config.ts` sets `workers` as configured for this branch; adjust for local stability vs speed.
