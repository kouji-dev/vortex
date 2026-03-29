# Local E2E (Playwright) for knowledge bases & chat — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a **local-only** Playwright harness: isolated Postgres via Docker (`local-e2e`), dev bearer auth, and specs that cover KB list/create, file upload on the KB detail page, and attaching a KB to a chat via the **live** UI (`KbsToolbarButton` + `KbPickerDialog` — not the unused `ConversationKnowledgeBasesPanel`).

**Architecture:** A second Compose file namespaces **`local-e2e`** with its own volume and host port. Engineers run Postgres in Docker, migrate against `ai_portal_e2e`, start `uvicorn` and `vite` on the host with `AUTH_MODE=dev` / `VITE_AUTH_MODE=dev`, then `npx playwright test`. Global setup hits `GET /health` on the API. Chat scenarios create an empty conversation via **`POST /api/chat/conversations`** (Playwright `request` fixture) so tests never need to send a first message or call the LLM.

**Tech stack:** Docker Compose, Playwright (`@playwright/test`), existing FastAPI (`/health`, `/api/...`), Vite dev server, Python 3.12 + Alembic for migrations.

**Spec:** `docs/superpowers/specs/2026-03-30-e2e-knowledge-bases-design.md`

---

## File map (create / modify)

| Path | Role |
|------|------|
| `docker-compose.e2e.yml` | `name: local-e2e`, pgvector Postgres, DB `ai_portal_e2e`, host port **5435** |
| `.gitignore` (repo root) | Ignore `.e2e-uploads/` |
| `frontend/package.json` | `devDependencies`: `@playwright/test`; scripts `test:e2e`, `test:e2e:ui` |
| `frontend/playwright.config.ts` | `baseURL`, `webServer` optional off by default, `globalSetup` |
| `frontend/e2e/global-setup.ts` | Poll `process.env.E2E_API_URL` + `/health` |
| `frontend/e2e/fixtures/sample-e2e.txt` | Tiny UTF-8 file for uploads |
| `frontend/e2e/README.md` | Env vars, compose + migrate + run order |
| `frontend/e2e/kb.spec.ts` | E2E-KB-1, E2E-KB-2 |
| `frontend/e2e/helpers/create-conversation.ts` | `POST /api/chat/conversations` for empty thread |
| `frontend/e2e/chat-kb.spec.ts` | E2E-CHAT-1 (picker flow) |
| `frontend/src/routes/knowledge-bases/$id.tsx` | `data-testid="kb-upload-input"` on file input |
| `frontend/src/components/knowledge-bases/KbPickerDialog.tsx` | `data-testid="kb-picker-search"` on search input (optional stability) |

---

### Task 1: `local-e2e` Postgres Compose

**Files:**
- Create: `docker-compose.e2e.yml`

- [ ] **Step 1: Add compose file**

Create `docker-compose.e2e.yml` at the repo root:

```yaml
# Isolated stack for Playwright / manual E2E. Does not touch local-dev volumes.
# Usage: docker compose -f docker-compose.e2e.yml up -d
name: local-e2e

services:
  db:
    image: pgvector/pgvector:pg17
    container_name: local-e2e-ai-portal-db
    restart: unless-stopped
    environment:
      POSTGRES_DB: ai_portal_e2e
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "127.0.0.1:5435:5432"
    volumes:
      - ai-portal-e2e-db-data:/var/lib/postgresql/data

volumes:
  ai-portal-e2e-db-data:
```

**Local `DATABASE_URL` for Alembic and uvicorn:**

`postgresql+psycopg://postgres:postgres@127.0.0.1:5435/ai_portal_e2e`

- [ ] **Step 2: Commit**

```bash
git add docker-compose.e2e.yml
git commit -m "chore(e2e): add local-e2e Postgres compose"
```

---

### Task 2: Gitignore E2E upload dir

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Append**

Add a line:

```
.e2e-uploads/
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore(e2e): gitignore local E2E upload directory"
```

---

### Task 3: Playwright package + scripts

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install**

From `frontend/`:

```bash
npm install -D @playwright/test
npx playwright install
```

- [ ] **Step 2: Add scripts** to `package.json` `"scripts"`:

```json
"test:e2e": "playwright test",
"test:e2e:ui": "playwright test --ui"
```

- [ ] **Step 3: Commit** `package.json` and `package-lock.json`

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(e2e): add Playwright devDependency and npm scripts"
```

---

### Task 4: Playwright config + global setup

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/global-setup.ts`

- [ ] **Step 1: `frontend/e2e/global-setup.ts`**

```typescript
export default async function globalSetup() {
  const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8000'
  const url = `${base.replace(/\/$/, '')}/health`
  const deadline = Date.now() + 60_000
  let lastErr: unknown
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url)
      if (res.ok) return
      lastErr = new Error(`health not ok: ${res.status}`)
    } catch (e) {
      lastErr = e
    }
    await new Promise((r) => setTimeout(r, 500))
  }
  throw lastErr instanceof Error ? lastErr : new Error(String(lastErr))
}
```

- [ ] **Step 2: `frontend/playwright.config.ts`**

```typescript
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: 'e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  globalSetup: './e2e/global-setup.ts',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
```

Note: `forbidOnly` uses `CI` harmlessly; no GitHub job is required by this plan.

- [ ] **Step 3: Commit**

```bash
git add frontend/playwright.config.ts frontend/e2e/global-setup.ts
git commit -m "chore(e2e): Playwright config and health global setup"
```

---

### Task 5: E2E README + fixture file

**Files:**
- Create: `frontend/e2e/README.md`
- Create: `frontend/e2e/fixtures/sample-e2e.txt`

- [ ] **Step 1: Fixture content** (`frontend/e2e/fixtures/sample-e2e.txt`)

```
E2E fixture document for knowledge base upload tests.
```

- [ ] **Step 2: README** — document this sequence (adjust paths if your shell differs):

1. `docker compose -f docker-compose.e2e.yml up -d`
2. Export `DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5435/ai_portal_e2e` and from `backend/` run `alembic upgrade head`
3. Start API from `backend/` with at least: `AUTH_MODE=dev`, `DEV_BEARER_TOKEN=devtoken`, `DEV_SEED_USER_EMAIL=dev@localhost`, `UPLOAD_DIR` pointing to a repo-local `.e2e-uploads` directory (create it once)
4. Start frontend from `frontend/` with: `VITE_AUTH_MODE=dev`, `VITE_DEV_BEARER_TOKEN=devtoken`, `VITE_API_URL=http://127.0.0.1:8000` (or your API port)
5. Export `E2E_API_URL=http://127.0.0.1:8000` and run `npm run test:e2e`

**Ingest / embeddings:** `ingest_document` calls `embedding_svc.embed_texts`. Without a key, ingest typically sets document status to **`failed`** after errors. Tests should **poll** the Documents table until status is not a loading state, then accept **`ready`** (if keys set) or **`failed`** (no keys) while still requiring the **filename** to match the upload.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/README.md frontend/e2e/fixtures/sample-e2e.txt
git commit -m "docs(e2e): local runbook and upload fixture"
```

---

### Task 6: Stable selectors (`data-testid`)

**Files:**
- Modify: `frontend/src/routes/knowledge-bases/$id.tsx`
- Modify: `frontend/src/components/knowledge-bases/KbPickerDialog.tsx` (optional but recommended)

- [ ] **Step 1: KB detail file input** — on the `<input type="file" ...>` inside the “Upload documents” section, add:

```tsx
data-testid="kb-upload-input"
```

- [ ] **Step 2: KB picker search** — on the search `<input>` in `KbPickerDialog`, add:

```tsx
data-testid="kb-picker-search"
```

- [ ] **Step 3: Run frontend build**

```bash
cd frontend && npm run build
```

Expected: success (no TS errors).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/knowledge-bases/$id.tsx frontend/src/components/knowledge-bases/KbPickerDialog.tsx
git commit -m "test(e2e): add data-testid hooks for KB upload and picker"
```

---

### Task 7: Spec `kb.spec.ts` (list, create, upload)

**Files:**
- Create: `frontend/e2e/kb.spec.ts`

- [ ] **Step 1: Implement**

Use a unique KB name per run, e.g. `E2E KB ${Date.now()}`.

Flow:

1. `await page.goto('/knowledge-bases')`
2. Click **Add knowledge base** (`getByRole('button', { name: /add knowledge base/i })`)
3. Dialog: fill **Name** via `getByRole('textbox', { name: /^name$/i })` or label association; **Description** optional
4. Click **Next**
5. Step 2: ensure **Files** / `files` connector is selected (default if already selected), click **Create**
6. Wait for navigation to `/knowledge-bases/$id` and `h1` containing the name
7. `await page.getByTestId('kb-upload-input').setInputFiles('e2e/fixtures/sample-e2e.txt')`
8. Poll: within `expect(...).toPass({ timeout: 120_000 })`, locate row with cell text `sample-e2e.txt` and assert status text is **`ready`** OR **`failed`** (see README); never assert permanent **`pending`** without timeout

Example skeleton (resolve fixture path with `import.meta.url` because `frontend/package.json` is `"type": "module"`):

```typescript
import { test, expect } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

test.describe('Knowledge bases', () => {
  test('create KB and upload document', async ({ page }) => {
    const name = `E2E KB ${Date.now()}`
    await page.goto('/knowledge-bases')
    await page.getByRole('button', { name: /add knowledge base/i }).click()
    await page.getByRole('textbox', { name: /^name$/i }).fill(name)
    await page.getByRole('button', { name: 'Next' }).click()
    await page.getByRole('button', { name: 'Create' }).click()
    await expect(page.getByRole('heading', { level: 1, name })).toBeVisible()

    const filePath = path.join(__dirname, 'fixtures', 'sample-e2e.txt')
    await page.getByTestId('kb-upload-input').setInputFiles(filePath)

    await expect(async () => {
      const row = page.getByRole('row', { name: /sample-e2e\.txt/ })
      await expect(row).toBeVisible()
      const status = row.getByRole('cell').nth(1)
      const t = (await status.textContent())?.trim() ?? ''
      expect(['ready', 'failed']).toContain(t)
    }).toPass({ timeout: 120_000 })
  })
})
```

Adjust selectors if the “Name” field is not exposed as a textbox with accessible name (use `page.locator` on the first step’s name input from `CreateKnowledgeBaseDialog` as fallback).

- [ ] **Step 2: Run** (with stack up per README)

```bash
cd frontend
set E2E_API_URL=http://127.0.0.1:8000
npm run test:e2e -- kb.spec.ts
```

Expected: **1 passed** (or fix selectors).

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/kb.spec.ts
git commit -m "test(e2e): knowledge base create and file upload"
```

---

### Task 8: Helper + spec `chat-kb.spec.ts` (picker attach)

**Files:**
- Create: `frontend/e2e/helpers/create-conversation.ts`
- Create: `frontend/e2e/chat-kb.spec.ts`

- [ ] **Step 1: `frontend/e2e/helpers/create-conversation.ts`**

Bearer token must match `DEV_BEARER_TOKEN` (default `devtoken`).

```typescript
import type { APIRequestContext } from '@playwright/test'

export async function createEmptyConversation(
  request: APIRequestContext,
  apiBase: string,
): Promise<number> {
  const base = apiBase.replace(/\/$/, '')
  const res = await request.post(`${base}/api/chat/conversations`, {
    headers: { Authorization: 'Bearer devtoken' },
    data: { title: 'E2E', model: null, assistant_id: null, settings: null },
  })
  if (!res.ok()) {
    throw new Error(`create conversation failed: ${res.status()} ${await res.text()}`)
  }
  const body = (await res.json()) as { id: number }
  return body.id
}
```

- [ ] **Step 2: `frontend/e2e/chat-kb.spec.ts`**

Use `test.describe.configure({ mode: 'serial' })`. First test: create a KB through the UI (same steps as Task 7 but **no file upload**), store `kbName` in a module-level `let`. Second test: `createEmptyConversation`, `page.goto('/chat/conversations/' + id)`, click `getByRole('button', { name: 'Knowledge bases' })`, wait for `kb-picker-search`, click the `role="option"` row whose text includes `kbName`, wait for network idle or absence of `Saving…`, assert toolbar `getByRole('button', { name: /1 KBs active|1 knowledge base active/i })`, reload, reopen picker, assert **● active** for that KB.

- [ ] **Step 3: Run**

```bash
cd frontend
set E2E_API_URL=http://127.0.0.1:8000
npm run test:e2e -- chat-kb.spec.ts
```

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/chat-kb.spec.ts frontend/e2e/helpers/create-conversation.ts
git commit -m "test(e2e): attach knowledge base from chat picker"
```

---

## Spec self-review (plan vs `2026-03-30-e2e-knowledge-bases-design.md`)

| Spec item | Plan task |
|-----------|-----------|
| `docker-compose.e2e.yml`, `local-e2e`, isolated DB | Task 1 |
| Dev auth (no Entra) | README Task 5; tests use dev token / Vite dev mode |
| KB list / create / upload | Task 7 |
| Chat KB attachment | Task 8 (`KbPickerDialog`, not legacy panel) |
| Local-only (no GitHub CI) | No CI task; config uses `CI` only for `forbidOnly` |
| Fixtures + polling ingest | Task 5 + Task 7 |
| `data-testid` minimal set | Task 6 |

**Placeholder scan:** None intentional; embedding behavior documented as `ready` vs `failed`.

---

## Execution handoff

**Plan complete and saved to `docs/superpowers/plans/2026-03-30-e2e-knowledge-bases.md`. Two execution options:**

**1. Subagent-driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline execution** — Run tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach do you want?**
