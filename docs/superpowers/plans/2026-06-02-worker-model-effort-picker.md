# Worker Model & Effort Picker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the worker spawn form's free-text model input + "Agent SDK" runtime select with two catalog-driven selects — **Model** (filtered by a new `usable_in_worker` flag) and **Effort** (Low/Medium/High/Max) — and infer the agent runtime from the chosen model.

**Architecture:** Add a `usable_in_worker` boolean to the catalog (`catalog_models`), surface it in `GET /api/models` (+ a filter), and consume it in `SpawnDrawer`. The runtime (`claude`/`codex`) is derived from the model's provider/`api_model_id` instead of being picked. `effort` is added to the spawn request body.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend), React + TanStack Query + the shared `~/components/ui/select` (frontend), Playwright (E2E against the mock-server).

Spec: `docs/superpowers/specs/2026-06-02-worker-creation-git-connection-design.md` (§1, §2).

---

### Task 1: Add `usable_in_worker` column to the catalog model

**Files:**
- Modify: `server/api/src/ai_portal/catalog/model.py` (the `CatalogModel` class, after `requires_entitlement`)
- Create: `server/api/alembic/versions/073_catalog_usable_in_worker.py`
- Test: `server/api/tests/catalog/test_usable_in_worker.py`

- [ ] **Step 1: Write the failing test**

```python
# server/api/tests/catalog/test_usable_in_worker.py
from ai_portal.catalog.model import CatalogModel


def test_catalog_model_has_usable_in_worker_default_false():
    col = CatalogModel.__table__.c.usable_in_worker
    assert col is not None
    assert col.default.arg is False
    assert col.nullable is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server/api && python -m pytest tests/catalog/test_usable_in_worker.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'usable_in_worker'`

- [ ] **Step 3: Add the column**

In `server/api/src/ai_portal/catalog/model.py`, inside `CatalogModel`, after the `requires_entitlement` line, add:

```python
    usable_in_worker: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False, index=True
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server/api && python -m pytest tests/catalog/test_usable_in_worker.py -v`
Expected: PASS

- [ ] **Step 5: Write the Alembic migration**

```python
# server/api/alembic/versions/073_catalog_usable_in_worker.py
"""catalog: usable_in_worker flag (gates the worker model picker)."""
from alembic import op
import sqlalchemy as sa

revision = "073_catalog_usable_in_worker"
down_revision = "072_control_plane_ldap_connections"
branch_labels = None
depends_on = None

# api_model_id prefixes the agent CLIs can drive (Claude Agent SDK / Codex CLI).
_WORKER_PREFIXES = ("claude-",)
_WORKER_CONTAINS = ("codex",)


def upgrade() -> None:
    op.add_column(
        "catalog_models",
        sa.Column(
            "usable_in_worker",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_catalog_models_usable_in_worker", "catalog_models", ["usable_in_worker"]
    )
    # Seed: enable Claude + Codex rows (the agent CLIs can drive these).
    op.execute(
        "UPDATE catalog_models SET usable_in_worker = true "
        "WHERE api_model_id LIKE 'claude-%' OR api_model_id LIKE '%codex%'"
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_models_usable_in_worker", table_name="catalog_models")
    op.drop_column("catalog_models", "usable_in_worker")
```

- [ ] **Step 6: Apply the migration to the dev DB and verify**

Run:
```bash
cd server/api && DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5434/ai_portal" python -m alembic upgrade head
docker exec local-dev-ai-portal-db psql -U postgres -d ai_portal -c \
  "SELECT display_name, usable_in_worker FROM catalog_models WHERE usable_in_worker ORDER BY display_name;"
```
Expected: alembic reports `Running upgrade 072... -> 073...`; the query lists Claude + Codex rows with `usable_in_worker = t`.

- [ ] **Step 7: Commit**

```bash
git add server/api/src/ai_portal/catalog/model.py server/api/alembic/versions/073_catalog_usable_in_worker.py server/api/tests/catalog/test_usable_in_worker.py
git commit -m "feat(catalog): add usable_in_worker flag + migration"
```

---

### Task 2: Surface `usable_in_worker` in the catalog API + add a filter

**Files:**
- Modify: `server/api/src/ai_portal/catalog/schemas.py` (`CatalogModelRead`)
- Modify: `server/api/src/ai_portal/catalog/router.py` (`list_catalog_models`)
- Test: `server/api/tests/catalog/test_models_endpoint_worker_filter.py`

- [ ] **Step 1: Write the failing test**

```python
# server/api/tests/catalog/test_models_endpoint_worker_filter.py
def test_models_endpoint_supports_usable_in_worker_filter(client, seed_catalog):
    # seed_catalog must create >=1 worker model (claude-*) and >=1 non-worker (gemini-*).
    all_models = client.get("/api/models").json()
    worker_models = client.get("/api/models?usable_in_worker=true").json()

    assert any(m["usable_in_worker"] for m in all_models)
    assert len(worker_models) < len(all_models)
    assert all(m["usable_in_worker"] for m in worker_models)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server/api && python -m pytest tests/catalog/test_models_endpoint_worker_filter.py -v`
Expected: FAIL — response rows have no `usable_in_worker` key / unknown query param ignored.

- [ ] **Step 3: Add the field to `CatalogModelRead`**

In `server/api/src/ai_portal/catalog/schemas.py`, inside `CatalogModelRead`, after `accessible: bool` add:

```python
    usable_in_worker: bool = False
```

- [ ] **Step 4: Add the filter to `list_catalog_models`**

In `server/api/src/ai_portal/catalog/router.py`, add a query param and filter. The handler currently builds the row list; add the parameter to the signature and filter before serialization:

```python
def list_catalog_models(
    usable_in_worker: bool | None = None,
    # ...existing params...
):
    # ...existing query that yields `rows`...
    if usable_in_worker is not None:
        rows = [r for r in rows if r.usable_in_worker == usable_in_worker]
    # ...existing serialization to CatalogModelRead...
```

(If the handler maps ORM rows to `CatalogModelRead` explicitly, also copy `usable_in_worker=row.usable_in_worker` in that mapping.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd server/api && python -m pytest tests/catalog/test_models_endpoint_worker_filter.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add server/api/src/ai_portal/catalog/schemas.py server/api/src/ai_portal/catalog/router.py server/api/tests/catalog/test_models_endpoint_worker_filter.py
git commit -m "feat(catalog): expose usable_in_worker + ?usable_in_worker filter on /api/models"
```

---

### Task 3: Add `effort` to the spawn body + infer runtime server-side

**Files:**
- Modify: `server/api/src/ai_portal/workers/schemas.py` (`SpawnWorkerBody`)
- Create: `server/api/src/ai_portal/workers/runtime_infer.py`
- Test: `server/api/tests/workers/test_runtime_infer.py`

- [ ] **Step 1: Write the failing test**

```python
# server/api/tests/workers/test_runtime_infer.py
import pytest
from ai_portal.workers.runtime_infer import infer_runtime


@pytest.mark.parametrize(
    "api_model_id, expected",
    [
        ("claude-opus-4-7", "claude"),
        ("claude-sonnet-4-6", "claude"),
        ("gpt-5.4-codex", "codex"),
        ("gpt-5.3-codex", "codex"),
    ],
)
def test_infer_runtime(api_model_id, expected):
    assert infer_runtime(api_model_id) == expected


def test_infer_runtime_unknown_raises():
    with pytest.raises(ValueError):
        infer_runtime("gemini-3.1-pro")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server/api && python -m pytest tests/workers/test_runtime_infer.py -v`
Expected: FAIL — `ModuleNotFoundError: ai_portal.workers.runtime_infer`

- [ ] **Step 3: Implement `infer_runtime`**

```python
# server/api/src/ai_portal/workers/runtime_infer.py
"""Infer the agent runtime (CLI) from a model id. Only Claude + Codex models are
usable_in_worker, so the mapping is total over the worker catalog."""
from __future__ import annotations


def infer_runtime(api_model_id: str) -> str:
    mid = api_model_id.lower()
    if mid.startswith("claude-"):
        return "claude"
    if "codex" in mid:
        return "codex"
    raise ValueError(f"no agent runtime for model {api_model_id!r}")
```

- [ ] **Step 4: Add `effort` to `SpawnWorkerBody` and make `runtime` optional**

In `server/api/src/ai_portal/workers/schemas.py`, inside `SpawnWorkerBody`, change the `runtime` line and add `effort`:

```python
    runtime: str | None = Field(default=None, pattern="^(claude|codex)$")
    effort: str = Field(default="medium", pattern="^(low|medium|high|max)$")
```

- [ ] **Step 5: Use inference in the spawn service**

In `server/api/src/ai_portal/workers/instances_service.py` (the function called by `POST /v1/workers/instances`), resolve the runtime when not provided. Find where the body is turned into a worker and add, before persisting:

```python
from ai_portal.workers.runtime_infer import infer_runtime

runtime = body.runtime or infer_runtime(body.model)
```
Then pass `runtime` (not `body.runtime`) and persist `body.effort`.

- [ ] **Step 6: Run tests**

Run: `cd server/api && python -m pytest tests/workers/test_runtime_infer.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add server/api/src/ai_portal/workers/runtime_infer.py server/api/src/ai_portal/workers/schemas.py server/api/src/ai_portal/workers/instances_service.py server/api/tests/workers/test_runtime_infer.py
git commit -m "feat(workers): infer runtime from model, accept effort in spawn body"
```

---

### Task 4: Frontend types + worker-models hook

**Files:**
- Modify: `apps/frontend/src/lib/chat-types.ts` (`CatalogModelEntry`)
- Create: `apps/frontend/src/hooks/useWorkerModelsQuery.ts`
- Create: `apps/frontend/src/lib/worker-runtime.ts`
- Test: `apps/frontend/src/lib/worker-runtime.test.ts`

- [ ] **Step 1: Add `usable_in_worker` to `CatalogModelEntry`**

In `apps/frontend/src/lib/chat-types.ts`, inside `CatalogModelEntry` (after `is_default: boolean;`):

```typescript
  usable_in_worker?: boolean;
```

- [ ] **Step 2: Write the failing runtime-inference test**

```typescript
// apps/frontend/src/lib/worker-runtime.test.ts
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { inferRuntime } from './worker-runtime.ts'

test('inferRuntime maps claude + codex models', () => {
  assert.equal(inferRuntime('claude-opus-4-7'), 'claude')
  assert.equal(inferRuntime('gpt-5.4-codex'), 'codex')
  assert.equal(inferRuntime('gemini-3.1-pro'), null)
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd apps/frontend && node --test src/lib/worker-runtime.test.ts`
Expected: FAIL — cannot find `./worker-runtime.ts`

- [ ] **Step 4: Implement `inferRuntime`**

```typescript
// apps/frontend/src/lib/worker-runtime.ts
export type WorkerRuntime = 'claude' | 'codex'

/** Derive the agent runtime from a model id; null if the model can't drive a CLI. */
export function inferRuntime(apiModelId: string): WorkerRuntime | null {
  const id = apiModelId.toLowerCase()
  if (id.startsWith('claude-')) return 'claude'
  if (id.includes('codex')) return 'codex'
  return null
}
```

- [ ] **Step 5: Implement the worker-models hook**

```typescript
// apps/frontend/src/hooks/useWorkerModelsQuery.ts
import { useQuery } from '@tanstack/react-query'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import type { CatalogModelEntry } from '~/lib/chat-types'

/** Catalog models flagged usable_in_worker — the source for the worker model select. */
export function useWorkerModelsQuery() {
  const apiBase = getApiBase()
  return useQuery({
    queryKey: ['catalog', 'worker-models'],
    queryFn: async (): Promise<CatalogModelEntry[]> => {
      const res = await fetch(`${apiBase}/api/models?usable_in_worker=true`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json() as Promise<CatalogModelEntry[]>
    },
  })
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd apps/frontend && node --test src/lib/worker-runtime.test.ts`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add apps/frontend/src/lib/chat-types.ts apps/frontend/src/hooks/useWorkerModelsQuery.ts apps/frontend/src/lib/worker-runtime.ts apps/frontend/src/lib/worker-runtime.test.ts
git commit -m "feat(workers-ui): worker models hook + runtime inference"
```

---

### Task 5: Rebuild the SpawnDrawer model/effort/runtime controls

**Files:**
- Modify: `apps/frontend/src/routes/workers/instances.tsx` (`SpawnDrawer` + `RUNTIME_OPTIONS`)

- [ ] **Step 1: Add effort options + import the hook**

At the top of the file, add the import:

```typescript
import { useWorkerModelsQuery } from '~/hooks/useWorkerModelsQuery'
import { inferRuntime } from '~/lib/worker-runtime'
```

Near `MODE_OPTIONS`, add:

```typescript
const EFFORT_OPTIONS = ['low', 'medium', 'high', 'max'] as const
```

- [ ] **Step 2: Replace the model state + free-text input + runtime select**

In `SpawnDrawer`, replace the `model`/`runtime` state and the Model `<Field>` + Runtime `<Field>` blocks. New state (replace the `model` and `runtime` `useState` lines):

```typescript
  const workerModels = useWorkerModelsQuery()
  const [model, setModel] = React.useState('') // api_model_id
  const [effort, setEffort] = React.useState('medium')

  // Default to the first worker model once loaded.
  React.useEffect(() => {
    if (!model && workerModels.data && workerModels.data.length > 0) {
      setModel(workerModels.data[0].api_model_id)
      setEffort(workerModels.data[0].effort || 'medium')
    }
  }, [workerModels.data, model])

  const runtime = inferRuntime(model) ?? 'claude'
```

Replace the Model `<Field>` (the free-text input) with:

```tsx
        <Field label="Model">
          <Select
            style={{ width: '100%' }}
            value={model}
            onChange={(e) => setModel(e.target.value)}
            data-testid="wk-instance-spawn-model"
            size="sm"
          >
            {(workerModels.data ?? []).map((m) => (
              <option key={m.id} value={m.api_model_id}>
                {m.display_name}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Effort">
          <Select
            style={{ width: '100%' }}
            value={effort}
            onChange={(e) => setEffort(e.target.value)}
            data-testid="wk-instance-spawn-effort"
            size="sm"
          >
            {EFFORT_OPTIONS.map((e) => (
              <option key={e} value={e}>
                {e[0].toUpperCase() + e.slice(1)}
              </option>
            ))}
          </Select>
        </Field>
```

Delete the entire Runtime `<Field>` block and the `RUNTIME_OPTIONS` const (runtime is now inferred).

- [ ] **Step 3: Send `effort` in the spawn mutation**

In the `spawn` mutation's `api.spawnWorker({...})` call, add `effort` and keep the inferred `runtime`:

```typescript
      api.spawnWorker({
        name,
        model,
        effort,
        mode,
        runtime,
        repo_url: repoUrl || null,
        connector: { kind: 'gitlab', project: gitlabProject, branch },
      }),
```

- [ ] **Step 4: Add `effort` to the request type**

In `apps/frontend/src/lib/workers-api.ts`, add `effort: string` to the `SpawnWorkerRequest` type (find the type and add the field).

- [ ] **Step 5: Type-check**

Run: `cd apps/frontend && npx tsc --noEmit`
Expected: EXIT 0

- [ ] **Step 6: Commit**

```bash
git add apps/frontend/src/routes/workers/instances.tsx apps/frontend/src/lib/workers-api.ts
git commit -m "feat(workers-ui): catalog-driven Model + Effort selects, runtime inferred"
```

---

### Task 6: E2E test for the spawn form

**Files:**
- Create: `apps/frontend/e2e/workers/spawn-model-effort.spec.ts`
- Modify: `apps/frontend/e2e/support/mock-server.mjs` (serve `?usable_in_worker=true`)

- [ ] **Step 1: Make the mock honor the worker filter**

In `mock-server.mjs`, the `/api/models` handler currently returns `MOCK_MODELS`. Update it to support the filter and tag worker models. Replace the `/api/models` line:

```javascript
  if (path === '/api/models') {
    const url = new URL(req.url, 'http://x')
    const wantWorker = url.searchParams.get('usable_in_worker') === 'true'
    const tagged = MOCK_MODELS.map((m) => ({
      ...m,
      usable_in_worker: m.api_model_id.startsWith('claude-') || m.api_model_id.includes('codex'),
    }))
    return json(res, wantWorker ? tagged.filter((m) => m.usable_in_worker) : tagged)
  }
```

(`MOCK_MODELS` already includes `claude-haiku-4-5`, which satisfies the worker filter.)

- [ ] **Step 2: Write the E2E test**

```typescript
// apps/frontend/e2e/workers/spawn-model-effort.spec.ts
import { test, expect } from '../support/fixtures'

test.describe('Worker spawn — model & effort', () => {
  test('spawn drawer shows catalog model + effort selects, no runtime select', async ({ page }) => {
    await page.goto('/workers/instances', { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: /spawn/i }).first().click()

    const drawer = page.getByTestId('wk-instance-spawn-drawer')
    await expect(drawer).toBeVisible()

    const model = page.getByTestId('wk-instance-spawn-model')
    await expect(model).toBeVisible()
    // Only worker-flagged (Claude/Codex) models — no Gemini.
    await expect(model.locator('option', { hasText: /claude/i }).first()).toBeAttached()
    await expect(model.locator('option', { hasText: /gemini/i })).toHaveCount(0)

    await expect(page.getByTestId('wk-instance-spawn-effort')).toBeVisible()
    await expect(page.getByTestId('wk-instance-spawn-runtime')).toHaveCount(0)
  })
})
```

- [ ] **Step 3: Run the E2E test**

Run: `cd apps/frontend && pnpm test:e2e:filter spawn-model-effort`
Expected: PASS (1 test). If the Spawn button label differs, adjust the `getByRole` name to match `instances.tsx`.

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/e2e/workers/spawn-model-effort.spec.ts apps/frontend/e2e/support/mock-server.mjs
git commit -m "test(workers-ui): e2e for catalog-driven model + effort spawn controls"
```

---

## Self-Review

- **Spec coverage:** §1 catalog flag → Tasks 1–2; §2 model+effort selects + inferred runtime → Tasks 3–6. Git connection (§3–4) and execution provider (§5) are intentionally out of this plan (separate plans).
- **Type consistency:** `usable_in_worker` is the field name in the ORM (Task 1), schema (Task 2), and frontend type (Task 4). `infer_runtime`/`inferRuntime` return `'claude' | 'codex'`. `effort` ∈ `{low,medium,high,max}` in both backend (Task 3) and frontend (Task 5).
- **Open follow-ups (next plans):** admin toggle UI for `usable_in_worker`; effort → provider-parameter mapping at the gateway; replacing the GitLab/repo fields with the connected-repo picker (Plan 2).
