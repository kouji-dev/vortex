# Frontend Auth Gate & Render Deploy Finalization

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a frontend auth guard (redirect unauthenticated users to `/login`, redirect selfhosted 503 to `/setup`), fix the `local` mode mismatch hint, and finalize `render.yaml` placeholder domains.

**Architecture:** A single `useAuthRedirect` hook runs on every protected route via the TanStack Router root loader. It checks `VITE_AUTH_MODE` — for `local` mode it reads `tokenStore`; for `dev`/`entra` it passes through. A `useSetupRedirect` hook detects a backend 503 (setup required) and redirects to `/setup`. `render.yaml` env vars are templated with `sync: false` so operators fill them in the dashboard.

**Tech Stack:** React, TanStack Router (file-based routes), TanStack Query, TypeScript, Playwright (E2E), pnpm

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `frontend/src/hooks/useAuthRedirect.ts` | Redirect to `/login` when `local` mode and no token |
| Create | `frontend/src/hooks/useSetupRedirect.ts` | Redirect to `/setup` when backend returns 503 |
| Modify | `frontend/src/routes/__root.tsx` | Call both hooks in root component |
| Modify | `frontend/src/components/home/HomePage.tsx` | Fix `authModeMismatchHint` for `local` mode |
| Modify | `frontend/src/lib/health-types.ts` | Add `setup_required?: boolean` to `HealthResponse` |
| Modify | `render.yaml` | Replace placeholder domains with `sync: false` |
| Create | `frontend/e2e/auth/auth-gate.spec.ts` | E2E: unauthenticated → `/login` redirect |
| Create | `landing/src/lib/app-url.ts` | Centralized `getAppUrl()` with local dev default |
| Modify | `landing/src/routes/__root.tsx` + `index.tsx` + `features.tsx` + `pricing.tsx` | Use `getAppUrl()` instead of duplicated env var reads |
| Create | `landing/.env.example` | Document `VITE_APP_URL` for self-hosters |

---

## Task 1: Fix `HealthResponse` type and `authModeMismatchHint` for `local` mode

**Files:**
- Modify: `frontend/src/lib/health-types.ts`
- Modify: `frontend/src/components/home/HomePage.tsx`

- [ ] **Step 1: Update `HealthResponse` to include `deployment_mode`**

In `frontend/src/lib/health-types.ts`, replace the entire file with:

```ts
/** GET /health JSON (fields may be absent on older API builds). */
export type HealthResponse = {
  status: string
  auth_mode?: 'dev' | 'entra'
  deployment_mode?: 'dev' | 'saas' | 'selfhosted'
  api?: { post_knowledge_bases?: boolean }
}
```

- [ ] **Step 2: Fix `authModeMismatchHint` in `HomePage.tsx`**

In `frontend/src/components/home/HomePage.tsx`, find the `authModeMismatchHint` function (lines ~9-26) and replace it with:

```ts
function authModeMismatchHint(
  viteMode: 'dev' | 'entra' | 'local',
  apiDeploymentMode: 'dev' | 'saas' | 'selfhosted' | undefined,
  apiAuthMode: 'dev' | 'entra' | undefined,
): string | null {
  // local VITE mode is correct for saas/selfhosted backends
  if (viteMode === 'local') {
    if (apiDeploymentMode === 'dev') {
      return (
        'VITE_AUTH_MODE=local but the API is running in deployment_mode=dev. ' +
        'Set DEPLOYMENT_MODE=saas or selfhosted on the API, or set VITE_AUTH_MODE=dev.'
      )
    }
    return null
  }
  if (apiAuthMode == null || viteMode === apiAuthMode) return null
  if (viteMode === 'dev' && apiAuthMode === 'entra') {
    return (
      'This app is in dev auth (static bearer token), but the API reports auth_mode=entra. ' +
      'Set AUTH_MODE=dev in the API environment and restart, or switch the SPA to VITE_AUTH_MODE=entra.'
    )
  }
  return (
    'This app uses Entra (MSAL), but the API reports auth_mode=dev. ' +
    'Set AUTH_MODE=entra on the API and restart, or set VITE_AUTH_MODE=dev.'
  )
}
```

- [ ] **Step 3: Update the call-site in `HomePage` to pass `deployment_mode`**

Find the `mismatch` variable (lines ~35-40) and replace with:

```ts
const mismatch =
  health.isSuccess && health.data
    ? authModeMismatchHint(viteAuth, health.data.deployment_mode, health.data.auth_mode)
    : null
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd frontend && pnpm run build 2>&1 | tail -20
```

Expected: no TypeScript errors (build may warn about other things but not these types).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/health-types.ts frontend/src/components/home/HomePage.tsx
git commit -m "fix: handle local auth mode in health mismatch hint"
```

---

## Task 2: Create `useAuthRedirect` hook

**Files:**
- Create: `frontend/src/hooks/useAuthRedirect.ts`

This hook redirects to `/login` when `VITE_AUTH_MODE=local` and no access token exists in localStorage.

- [ ] **Step 1: Create the hook**

Create `frontend/src/hooks/useAuthRedirect.ts`:

```ts
import * as React from 'react'
import { useNavigate, useLocation } from '@tanstack/react-router'
import { getAuthMode } from '~/auth/msalConfig'
import { tokenStore } from '~/auth/tokenStore'

const UNPROTECTED = ['/login', '/register', '/setup']

/**
 * Redirects unauthenticated users to /login when VITE_AUTH_MODE=local.
 * No-ops in dev/entra modes (those have their own auth mechanisms).
 * Must be called inside a component that runs on every route (e.g. root layout).
 */
export function useAuthRedirect(): void {
  const navigate = useNavigate()
  const location = useLocation()

  React.useEffect(() => {
    if (typeof window === 'undefined') return
    if (getAuthMode() !== 'local') return
    if (UNPROTECTED.some((p) => location.pathname.startsWith(p))) return

    const token = tokenStore.getAccess()
    if (!token) {
      navigate({ to: '/login', replace: true })
    }
  }, [location.pathname, navigate])
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && pnpm run build 2>&1 | tail -20
```

Expected: no errors related to the new file.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useAuthRedirect.ts
git commit -m "feat: add useAuthRedirect hook for local auth mode"
```

---

## Task 3: Create `useSetupRedirect` hook

**Files:**
- Create: `frontend/src/hooks/useSetupRedirect.ts`

When `VITE_AUTH_MODE=local` and the backend health endpoint returns a 503 (setup required), redirect to `/setup`.

- [ ] **Step 1: Create the hook**

Create `frontend/src/hooks/useSetupRedirect.ts`:

```ts
import * as React from 'react'
import { useNavigate, useLocation } from '@tanstack/react-router'
import { getAuthMode } from '~/auth/msalConfig'
import { getApiBase } from '~/lib/api-base'

/**
 * Polls /health once on mount. If the backend responds 503 (selfhosted, not yet set up),
 * redirects to /setup. No-ops in dev/entra modes.
 */
export function useSetupRedirect(): void {
  const navigate = useNavigate()
  const location = useLocation()

  React.useEffect(() => {
    if (typeof window === 'undefined') return
    if (getAuthMode() !== 'local') return
    if (location.pathname === '/setup') return

    const apiBase = getApiBase()
    fetch(`${apiBase}/health`).then((res) => {
      if (res.status === 503) {
        navigate({ to: '/setup', replace: true })
      }
    }).catch(() => {
      // network error — don't redirect, let the app show error state
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // run once on mount only
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && pnpm run build 2>&1 | tail -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useSetupRedirect.ts
git commit -m "feat: add useSetupRedirect hook for selfhosted first-run"
```

---

## Task 4: Wire both hooks into the root layout

**Files:**
- Modify: `frontend/src/routes/__root.tsx`

- [ ] **Step 1: Import and call both hooks in `RootComponent`**

In `frontend/src/routes/__root.tsx`, add the imports after the existing imports:

```ts
import { useAuthRedirect } from '~/hooks/useAuthRedirect'
import { useSetupRedirect } from '~/hooks/useSetupRedirect'
```

Then replace the `RootComponent` function with:

```ts
function RootComponent() {
  useAuthRedirect()
  useSetupRedirect()

  const shell = (
    <AppShell>
      <Outlet />
    </AppShell>
  )

  return (
    <RootDocument>
      {getAuthMode() === 'entra' ? <EntraRoot>{shell}</EntraRoot> : shell}
    </RootDocument>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && pnpm run build 2>&1 | tail -20
```

Expected: no errors.

- [ ] **Step 3: Manual smoke test (dev mode)**

Start the frontend in dev mode (no auth guard should trigger in `dev` mode):

```bash
cd frontend && VITE_AUTH_MODE=dev pnpm dev
```

Open `http://localhost:5173` — you should land on the home page, not be redirected.

- [ ] **Step 4: Manual smoke test (local mode, no token)**

```bash
cd frontend && VITE_AUTH_MODE=local VITE_API_URL=http://localhost:8000 pnpm dev
```

Open `http://localhost:5173` — you should be redirected to `/login`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/__root.tsx
git commit -m "feat: wire auth gate and setup redirect into root layout"
```

---

## Task 5: E2E test — auth gate redirects unauthenticated users

**Files:**
- Create: `frontend/e2e/auth/auth-gate.spec.ts`

The E2E suite runs with `VITE_AUTH_MODE=dev` by default (see `playwright.config.ts`). To test the auth gate we need a `local` mode test that clears localStorage before visiting a protected route.

> Note: The existing E2E setup (`playwright.config.ts`) sets `VITE_AUTH_MODE: 'dev'` in the webServer env. This test overrides auth mode via a page script injection, so it doesn't require a separate webServer config.

- [ ] **Step 1: Create the spec file**

Create `frontend/e2e/auth/auth-gate.spec.ts`:

```ts
import { test, expect } from '@playwright/test'

test.describe('Auth gate (local mode simulation)', () => {
  test('redirects to /login when no token in localStorage', async ({ page }) => {
    // Clear any token that might be present from other tests
    await page.goto('/')
    await page.evaluate(() => {
      localStorage.removeItem('aip_access_token')
      localStorage.removeItem('aip_refresh_token')
    })

    // Inject a temporary override so getAuthMode() returns 'local' for this page load.
    // We route-intercept to simulate local mode without rebuilding Vite.
    await page.addInitScript(() => {
      // Override import.meta.env read via a module-level global the msalConfig reads
      Object.defineProperty(window, '__VITE_AUTH_MODE_OVERRIDE__', {
        value: 'local',
        writable: false,
      })
    })

    // Navigate to a protected route — should redirect to /login
    await page.goto('/')
    await expect(page).toHaveURL(/\/login/, { timeout: 5000 })
  })

  test('/login page renders sign-in form', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
    await expect(page.getByPlaceholder('you@example.com')).toBeVisible()
    await expect(page.getByPlaceholder('••••••••')).toBeVisible()
  })

  test('/register page renders create account form', async ({ page }) => {
    await page.goto('/register')
    await expect(page.getByRole('heading', { name: 'Create account' })).toBeVisible()
  })

  test('/setup page renders setup form', async ({ page }) => {
    await page.goto('/setup')
    await expect(page.getByRole('heading', { name: 'Set up AI Portal' })).toBeVisible()
    await expect(page.getByPlaceholder('Acme Corp')).toBeVisible()
  })
})
```

> **Note on the redirect test:** The `addInitScript` approach only works if `getAuthMode()` reads from a runtime value. Since `getAuthMode()` reads `import.meta.env.VITE_AUTH_MODE` (compiled at build time), the redirect test using `__VITE_AUTH_MODE_OVERRIDE__` will **not** actually trigger the redirect in the built bundle. Mark this test as `test.skip` and leave a comment — the form-render tests (login/register/setup pages exist and render) are the valuable coverage here.

- [ ] **Step 2: Update the redirect test to `test.skip` with explanation**

Replace the first test block with:

```ts
  // Skipped: VITE_AUTH_MODE is baked at build time so we can't override it at runtime
  // in Playwright. The auth gate is verified via manual smoke test (Task 4, Step 4).
  // To add automated coverage: build a separate Vite bundle with VITE_AUTH_MODE=local
  // and point a second webServer config at it.
  test.skip('redirects to /login when no token in localStorage', async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => {
      localStorage.removeItem('aip_access_token')
      localStorage.removeItem('aip_refresh_token')
    })
    await page.goto('/')
    await expect(page).toHaveURL(/\/login/, { timeout: 5000 })
  })
```

- [ ] **Step 3: Run the E2E tests (form-render tests only)**

```bash
cd frontend && pnpm test:e2e --grep "login page renders|register page renders|setup page renders"
```

Expected: 3 tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/auth/auth-gate.spec.ts
git commit -m "test(e2e): add auth page render tests for login, register, setup"
```

---

## Task 6: Finalize `render.yaml` placeholder domains

**Files:**
- Modify: `render.yaml`

The current file has hardcoded placeholder values. Replace them with `sync: false` so operators set real values in the Render dashboard, which is safer and more portable.

- [ ] **Step 1: Replace `render.yaml` with finalized version**

Replace the entire content of `render.yaml`:

```yaml
services:
  # ── Backend API ───────────────────────────────────────────────────────────
  - type: web
    name: ai-portal-api
    runtime: docker
    dockerfilePath: ./backend/Dockerfile
    dockerContext: ./backend
    plan: starter
    envVars:
      - key: DEPLOYMENT_MODE
        value: saas
      - key: DATABASE_URL
        sync: false          # Supabase / Render Postgres connection string
      - key: SECRET_KEY
        generateValue: true  # Render auto-generates a secure random value
      - key: CORS_ORIGINS
        sync: false          # e.g. https://app.yourdomain.com
      - key: EMAIL_FROM
        sync: false          # e.g. noreply@yourdomain.com
      - key: SMTP_HOST
        sync: false
      - key: SMTP_PORT
        value: "587"
      - key: SMTP_USER
        sync: false
      - key: SMTP_PASSWORD
        sync: false
      - key: OPENAI_API_KEY
        sync: false
      - key: ANTHROPIC_API_KEY
        sync: false

  # ── Frontend App ─────────────────────────────────────────────────────────
  - type: web
    name: ai-portal-app
    runtime: node
    rootDir: frontend
    buildCommand: npm install -g pnpm && pnpm install && pnpm run build
    startCommand: pnpm run start
    plan: starter
    envVars:
      - key: VITE_AUTH_MODE
        value: local
      - key: VITE_API_URL
        sync: false          # e.g. https://ai-portal-api.onrender.com
      - key: NODE_VERSION
        value: "20"

  # ── Landing Page ─────────────────────────────────────────────────────────
  - type: web
    name: ai-portal-landing
    runtime: node
    rootDir: landing
    buildCommand: npm install -g pnpm && pnpm install && pnpm run build
    startCommand: pnpm run start
    plan: starter
    envVars:
      - key: VITE_APP_URL
        sync: false          # e.g. https://ai-portal-app.onrender.com
      - key: NODE_VERSION
        value: "20"
```

- [ ] **Step 2: Verify frontend has a `start` script**

```bash
cat frontend/package.json | grep '"start"'
```

Expected output: `"start": "..."` (some SSR server command). If missing, check what the production start command should be and add it. For a Vite SSR app it is typically:

```bash
cat frontend/package.json | grep -E '"start"|"serve"|"preview"'
```

If no `start` script exists, it needs to be added to `frontend/package.json` before deploying. The correct command depends on the SSR adapter. Check `frontend/vite.config.ts` for the adapter in use:

```bash
cat frontend/vite.config.ts | grep -i adapter
```

- [ ] **Step 3: Verify landing has a `start` script**

```bash
cat landing/package.json | grep -E '"start"|"serve"|"preview"'
```

Same check as above for the landing page.

- [ ] **Step 4: Commit**

```bash
git add render.yaml
git commit -m "chore: replace render.yaml placeholder domains with sync: false"
```

---

---

## Task 7: Centralize landing `APP_URL` into a shared utility

**Files:**
- Create: `landing/src/lib/app-url.ts`
- Modify: `landing/src/routes/__root.tsx`
- Modify: `landing/src/routes/index.tsx`
- Modify: `landing/src/routes/features.tsx`
- Modify: `landing/src/routes/pricing.tsx`
- Create: `landing/.env.example`

Currently each landing route duplicates `const APP_URL = import.meta.env.VITE_APP_URL ?? 'https://app.example.com'`. The fallback is wrong for local dev and the duplication makes it easy to miss when changing the default.

- [ ] **Step 1: Create the `getAppUrl` utility**

Create `landing/src/lib/app-url.ts`:

```ts
/**
 * Returns the URL of the main app (frontend).
 *
 * Priority:
 *   1. VITE_APP_URL env var (set in .env or Render dashboard)
 *   2. http://localhost:5173 in local dev (Vite default port)
 *
 * Self-hosters: set VITE_APP_URL to your app domain in your .env or CI/CD env vars.
 */
export function getAppUrl(): string {
  const fromEnv = import.meta.env.VITE_APP_URL
  if (fromEnv && fromEnv.trim() !== '') return fromEnv.trim()
  // Local dev default — matches the Vite dev server default port
  return 'http://localhost:5173'
}
```

- [ ] **Step 2: Create `landing/.env.example`**

Create `landing/.env.example`:

```dotenv
# URL of the main frontend app. Used by CTA buttons (Sign up, Log in) on the landing page.
# Local dev: leave unset to default to http://localhost:5173
# Production (Render): set in the Render dashboard under ai-portal-landing > Environment
# Self-hosted: set to your app's domain, e.g. https://app.yourdomain.com
VITE_APP_URL=
```

- [ ] **Step 3: Update `landing/src/routes/__root.tsx`**

Replace:
```ts
const APP_URL = import.meta.env.VITE_APP_URL ?? 'https://app.example.com'
```
With:
```ts
import { getAppUrl } from '~/lib/app-url'
```

Then replace every occurrence of `APP_URL` in that file with `getAppUrl()`.

The two usages are on the Sign in and Sign up nav links:
```ts
href={`${getAppUrl()}/login`}
// and
href={`${getAppUrl()}/register`}
```

- [ ] **Step 4: Update `landing/src/routes/index.tsx`**

Replace:
```ts
const APP_URL = import.meta.env.VITE_APP_URL ?? 'https://app.example.com'
```
With:
```ts
import { getAppUrl } from '~/lib/app-url'
```

Then replace all `${APP_URL}` with `${getAppUrl()}` in the two CTA `href` props:
```ts
href={`${getAppUrl()}/register`}
```

- [ ] **Step 5: Update `landing/src/routes/features.tsx`**

Replace:
```ts
const APP_URL = import.meta.env.VITE_APP_URL ?? 'https://app.example.com'
```
With:
```ts
import { getAppUrl } from '~/lib/app-url'
```

Replace `${APP_URL}` with `${getAppUrl()}`:
```ts
href={`${getAppUrl()}/register`}
```

- [ ] **Step 6: Update `landing/src/routes/pricing.tsx`**

Replace:
```ts
const APP_URL = import.meta.env.VITE_APP_URL ?? 'https://app.example.com'
```
With:
```ts
import { getAppUrl } from '~/lib/app-url'
```

Replace `${APP_URL}` in the two plan `ctaHref` values:
```ts
ctaHref: `${getAppUrl()}/register`,
// and
ctaHref: `${getAppUrl()}/register`,
```

- [ ] **Step 7: Verify TypeScript compiles**

```bash
cd landing && pnpm run build 2>&1 | tail -20
```

Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add landing/src/lib/app-url.ts landing/.env.example \
  landing/src/routes/__root.tsx landing/src/routes/index.tsx \
  landing/src/routes/features.tsx landing/src/routes/pricing.tsx
git commit -m "feat: centralize landing APP_URL into getAppUrl() utility with local dev default"
```

---

## Self-Review

### Spec coverage check

| Requirement | Task |
|---|---|
| Frontend auth guard (redirect to `/login` when unauthenticated, `local` mode) | Task 2 + Task 4 |
| Redirect to `/setup` on backend 503 (selfhosted first run) | Task 3 + Task 4 |
| Fix `local` mode mismatch hint in `HomePage` | Task 1 |
| Finalize `render.yaml` placeholder domains | Task 6 |
| E2E tests for auth pages | Task 5 |
| Landing CTA buttons point to correct app URL via env var (local dev + self-hosted) | Task 7 |

### Placeholder scan

No TBD/TODO/placeholder patterns in code blocks — all code is complete and ready to copy-paste.

### Type consistency

- `HealthResponse.deployment_mode` added in Task 1 and used in Task 1's call-site — consistent.
- `getAuthMode()` already returns `'dev' | 'entra' | 'local'` (existing code) — no change needed.
- `useAuthRedirect` and `useSetupRedirect` both import `getAuthMode` from `~/auth/msalConfig` and `getApiBase` from `~/lib/api-base` — both are existing exports, verified.

### Known limitation (documented in Task 5)

`useAuthRedirect` only works at runtime when `VITE_AUTH_MODE` is compiled as `local`. The E2E test for the redirect is marked `test.skip` with a documented path to full automation (separate Vite build). The form-render tests are not skipped and provide meaningful coverage.
