# Dead Auth Code Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all dead code left over from the removed auth features (SCIM, LDAP/Directory, SAML, Entra/MSAL, Okta, MFA/TOTP, dev auth_mode) from both frontend and backend; clean stale comments; verify build passes.

**Architecture:** The live auth surface is: password, GitHub/Google social, enterprise OIDC SSO (`/v1/auth/sso/*`), and API keys. The `idp_connections` table and model stay (OIDC SSO uses them). The SSO admin page (`sso.tsx`) calls `/v1/idp-connections` which does NOT exist — it is dead. SCIM and LDAP admin pages call endpoints that also do not exist. All three pages + their support libs are removed. Backend dead code is limited to orphaned permission strings, a stale exempt path, a dead limiter, and stale comments.

**Tech Stack:** TypeScript/React (TanStack Router), Python/FastAPI, pnpm, Vite, tsr (TanStack Router route tree generator)

## Ground Constraints

- Never delete `idp_connections` table, ORM model, or SSO routes (`/v1/auth/sso/start`, `/v1/auth/sso/callback/{kind}`) — OIDC SSO is live
- Never delete `strategies/dev.py` — `UserManager` is used by auth routes
- Never delete `authorizedFetch.ts` — used everywhere
- Build must pass: `pnpm exec tsc --noEmit && pnpm build` from `apps/frontend/`
- Backend import check: `PYTHONPATH=src DEPLOYMENT_MODE=saas SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx .venv/Scripts/python.exe -c "import ai_portal.main"`
- `pnpm exec tsr generate` must run after route files are removed to regenerate `routeTree.gen.ts`
- When unsure about a symbol being live, grep for callers before deleting

---

### Task 1: Remove admin/sso.tsx, admin/directory.tsx, admin/scim.tsx route pages

**Files:**
- Delete: `apps/frontend/src/routes/admin/sso.tsx`
- Delete: `apps/frontend/src/routes/admin/directory.tsx`
- Delete: `apps/frontend/src/routes/admin/scim.tsx`
- Modify: `apps/frontend/src/routes/admin/route.tsx`

**Rationale:**
- `sso.tsx` calls `createIdpConnection` / `fetchIdpConnections` etc. → `/v1/idp-connections` — NOT a live route
- `directory.tsx` calls `fetchLdapConnections` etc. → `/v1/ldap-connections` — NOT a live route
- `scim.tsx` calls `fetchScimEndpoints` etc. → `/v1/scim/endpoints` — NOT a live route
- The nav in `route.tsx` has entries for all three that must be removed

- [ ] **Step 1: Remove the three page files**

```bash
rm apps/frontend/src/routes/admin/sso.tsx
rm apps/frontend/src/routes/admin/directory.tsx
rm apps/frontend/src/routes/admin/scim.tsx
```

- [ ] **Step 2: Remove nav entries from route.tsx**

In `apps/frontend/src/routes/admin/route.tsx`, remove these three entries from the `SECTIONS` array:

```tsx
  { to: '/admin/sso', label: 'SSO', testId: 'admin-nav-sso' },
  { to: '/admin/directory', label: 'Directory', testId: 'admin-nav-directory' },
  { to: '/admin/scim', label: 'SCIM', testId: 'admin-nav-scim' },
```

After edit, the comment on line 19 `// All admin sections enabled (O1-O10 + SCIM).` should become:
```tsx
// Active admin sections (SSO / Directory / SCIM management removed — no live backend routes).
```

- [ ] **Step 3: Regenerate routeTree.gen.ts**

```bash
cd apps/frontend && pnpm exec tsr generate
```

Expected: `routeTree.gen.ts` regenerated without references to AdminSso, AdminDirectory, AdminScim routes.

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/src/routes/admin/route.tsx apps/frontend/src/routeTree.gen.ts
git add -u apps/frontend/src/routes/admin/sso.tsx apps/frontend/src/routes/admin/directory.tsx apps/frontend/src/routes/admin/scim.tsx
git commit -m "chore(web): remove dead SSO/Directory/SCIM admin pages (no live backend routes)"
```

---

### Task 2: Remove dead lib files (idp-config, scim-form) and their tests

**Files:**
- Delete: `apps/frontend/src/lib/idp-config.ts`
- Delete: `apps/frontend/src/lib/idp-config.test.ts`
- Delete: `apps/frontend/src/lib/scim-form.ts`
- Delete: `apps/frontend/src/lib/scim-form.test.ts`

**Rationale:**
- `idp-config.ts` exports `getIdpFields`, `validateIdpConfig`, `SAML_FIELDS`, `ENTRA_FIELDS`, `OKTA_FIELDS` — only imported by `sso.tsx` (deleted in Task 1)
- `scim-form.ts` exports `SCIM_PRESETS`, `scimBaseUrl`, etc. — only imported by `scim.tsx` (deleted in Task 1)
- Both test files only test deleted functionality

Verify there are no remaining importers before deleting:
```bash
grep -rn "idp-config\|scim-form" apps/frontend/src --include="*.ts" --include="*.tsx"
```
Expected: only the test files themselves import these modules (after Task 1).

- [ ] **Step 1: Verify no live callers remain**

```bash
cd apps/frontend && grep -rn "idp-config\|scim-form" src --include="*.ts" --include="*.tsx"
```

Expected output: only the `*.test.ts` files for each. If any other callers remain, investigate before deleting.

- [ ] **Step 2: Delete the files**

```bash
rm apps/frontend/src/lib/idp-config.ts
rm apps/frontend/src/lib/idp-config.test.ts
rm apps/frontend/src/lib/scim-form.ts
rm apps/frontend/src/lib/scim-form.test.ts
```

- [ ] **Step 3: Commit**

```bash
git add -u apps/frontend/src/lib/idp-config.ts apps/frontend/src/lib/idp-config.test.ts apps/frontend/src/lib/scim-form.ts apps/frontend/src/lib/scim-form.test.ts
git commit -m "chore(web): remove idp-config and scim-form libs (callers deleted in prior commit)"
```

---

### Task 3: Prune dead types and LDAP/SCIM/IdP functions from admin-types.ts and admin-api.ts

**Files:**
- Modify: `apps/frontend/src/lib/admin-types.ts`
- Modify: `apps/frontend/src/lib/admin-api.ts`

**What to remove from admin-types.ts:**
- `IdpKind` — remove `'saml' | 'entra' | 'okta'` options. After: `export type IdpKind = 'oidc' | 'google'`
  - Keep `IdpKind` itself — it is still referenced in `auth/idp/model.py` context. However: check whether any live frontend code uses it after Task 1. If not, remove entire `IdpKind` + `IdpConnection` types + `CreateIdpConnectionRequest` + `UpdateIdpConnectionRequest` block (lines 34–64).
- `ScimPreset`, `ScimEndpoint`, `ScimEndpointCreated`, `ScimEndpointCreateRequest`, `ScimGroupRoleMapRequest`, `ScimGroup` — the entire `// ---------- SCIM ----------` block (lines 340–373)
- `LdapKind`, `LdapTlsMode`, `LdapConnection`, `CreateLdapConnectionRequest`, `UpdateLdapConnectionRequest`, `LdapTestResult` — the entire `// ---------- Directory / LDAP ----------` block (lines 457–514)
- `AuthConfig.directory` field — set `directory: false` default is fine, but if the field is only populated by the backend for LDAP which is removed, we should note it (keep the field for now as it comes from the live `/v1/auth/config` response — see ambiguous section in report)

**What to remove from admin-api.ts:**
- `fetchIdpConnections`, `createIdpConnection`, `updateIdpConnection`, `deleteIdpConnection` — the `// ---------- SSO ----------` block
- `fetchScimEndpoints`, `createScimEndpoint`, `revokeScimEndpoint`, `upsertScimGroupRole` — the `// ---------- SCIM ----------` block
- `fetchLdapConnections`, `createLdapConnection`, `updateLdapConnection`, `deleteLdapConnection`, `testLdapConnection` — the `// ---------- Directory / LDAP ----------` block
- Corresponding import type removals from `admin-types.ts` at top of `admin-api.ts`

- [ ] **Step 1: Verify no live callers of IdpConnection types**

```bash
cd apps/frontend && grep -rn "IdpConnection\|IdpKind\|fetchIdpConnections\|createIdpConnection\|updateIdpConnection\|deleteIdpConnection" src --include="*.ts" --include="*.tsx" | grep -v "admin-types\|admin-api"
```

Expected: no output (after Task 1 deleted sso.tsx).

- [ ] **Step 2: Verify no live callers of SCIM types/fns**

```bash
cd apps/frontend && grep -rn "ScimPreset\|ScimEndpoint\|fetchScimEndpoints\|createScimEndpoint\|revokeScimEndpoint\|upsertScimGroupRole" src --include="*.ts" --include="*.tsx" | grep -v "admin-types\|admin-api"
```

Expected: no output.

- [ ] **Step 3: Verify no live callers of LDAP types/fns**

```bash
cd apps/frontend && grep -rn "LdapConnection\|LdapKind\|LdapTlsMode\|fetchLdapConnections\|createLdapConnection\|updateLdapConnection\|deleteLdapConnection\|testLdapConnection" src --include="*.ts" --include="*.tsx" | grep -v "admin-types\|admin-api"
```

Expected: no output.

- [ ] **Step 4: Remove IdpConnection block from admin-types.ts (lines 34–64)**

Remove these lines from `apps/frontend/src/lib/admin-types.ts`:
```typescript
// ---------- SSO / IdP ----------
export type IdpKind = 'oidc' | 'saml' | 'entra' | 'okta' | 'google'

export interface IdpConnection {
  id: string
  kind: IdpKind
  name: string
  enabled: boolean
  sso_required: boolean
  domain: string | null
  config: Record<string, string>
  created_at: string
}

export interface CreateIdpConnectionRequest {
  kind: IdpKind
  name: string
  domain?: string | null
  config: Record<string, string>
  enabled?: boolean
  sso_required?: boolean
}

export interface UpdateIdpConnectionRequest {
  name?: string
  domain?: string | null
  config?: Record<string, string>
  enabled?: boolean
  sso_required?: boolean
}
```

- [ ] **Step 5: Remove SCIM block from admin-types.ts (lines 340–373)**

Remove these lines from `apps/frontend/src/lib/admin-types.ts`:
```typescript
// ---------- SCIM ----------
export type ScimPreset = 'generic' | 'okta' | 'entra'

export interface ScimEndpoint {
  id: string
  org_id: string
  name: string
  preset: ScimPreset
  enabled: boolean
  last_sync_at: string | null
  created_at: string
  revoked_at: string | null
}

export interface ScimEndpointCreated extends ScimEndpoint {
  token: string // shown once
}

export interface ScimEndpointCreateRequest {
  name: string
  preset?: ScimPreset
}

export interface ScimGroupRoleMapRequest {
  display_name: string
  role_name: MemberRole | 'service'
}

export interface ScimGroup {
  id: string
  display_name: string
  external_id: string | null
  role_name: string | null
}
```

- [ ] **Step 6: Remove LDAP block from admin-types.ts (lines 457–514)**

Remove these lines from `apps/frontend/src/lib/admin-types.ts`:
```typescript
// ---------- Directory / LDAP ----------
export type LdapKind = 'ldap' | 'active_directory'
export type LdapTlsMode = 'none' | 'starttls' | 'ldaps'

export interface LdapConnection {
  id: string
  org_id: string | null
  name: string
  kind: LdapKind
  host: string
  port: number
  bind_dn: string
  base_dn: string
  user_filter: string
  group_filter: string | null
  tls_mode: LdapTlsMode
  attr_map: Record<string, string> | null
  group_role_map: Record<string, string> | null
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface CreateLdapConnectionRequest {
  name: string
  kind?: LdapKind
  host: string
  port?: number | null
  bind_dn: string
  bind_secret: string
  base_dn: string
  user_filter?: string | null
  group_filter?: string | null
  tls_mode?: LdapTlsMode
  attr_map?: Record<string, string> | null
  group_role_map?: Record<string, string> | null
  enabled?: boolean
}

export interface UpdateLdapConnectionRequest {
  name?: string
  host?: string
  port?: number | null
  bind_dn?: string
  bind_secret?: string
  base_dn?: string
  user_filter?: string | null
  group_filter?: string | null
  tls_mode?: LdapTlsMode
  attr_map?: Record<string, string> | null
  group_role_map?: Record<string, string> | null
  enabled?: boolean
}

export interface LdapTestResult {
  ok: boolean
  message: string | null
}
```

- [ ] **Step 7: Remove dead API functions from admin-api.ts**

In `apps/frontend/src/lib/admin-api.ts`:

Remove the `// ---------- SSO ----------` section (fetchIdpConnections, createIdpConnection, updateIdpConnection, deleteIdpConnection).

Remove the `// ---------- SCIM ----------` section (fetchScimEndpoints, createScimEndpoint, revokeScimEndpoint, upsertScimGroupRole).

Remove the `// ---------- Directory / LDAP ----------` section (fetchLdapConnections, createLdapConnection, updateLdapConnection, deleteLdapConnection, testLdapConnection).

Also remove the now-dead type imports from the `import type { ... } from '~/lib/admin-types'` block at the top of `admin-api.ts`. Specifically remove: `IdpConnection`, `CreateIdpConnectionRequest`, `UpdateIdpConnectionRequest`, `ScimEndpoint`, `ScimEndpointCreated`, `ScimEndpointCreateRequest`, `ScimGroupRoleMapRequest`, `ScimGroup`, `LdapConnection`, `CreateLdapConnectionRequest`, `UpdateLdapConnectionRequest`, `LdapTestResult`.

- [ ] **Step 8: TypeScript check**

```bash
cd apps/frontend && pnpm exec tsc --noEmit
```

Expected: no errors. If there are errors, they indicate remaining callers — fix those before proceeding.

- [ ] **Step 9: Commit**

```bash
git add apps/frontend/src/lib/admin-types.ts apps/frontend/src/lib/admin-api.ts
git commit -m "chore(web): prune dead IdpConnection/SCIM/LDAP types and API functions"
```

---

### Task 4: Clean dead code in health-types.ts and auth-strategies.ts

**Files:**
- Modify: `apps/frontend/src/lib/health-types.ts`
- Modify: `apps/frontend/src/lib/auth-strategies.ts`
- Modify: `apps/frontend/src/lib/auth-strategies.test.ts`

**What to do:**

**health-types.ts** — Remove `auth_mode?: 'dev' | 'entra'`. The backend no longer returns this field (it was removed with Entra/dev mode). Current file:
```typescript
export type HealthResponse = {
  status: string
  auth_mode?: 'dev' | 'entra'
  deployment_mode?: 'dev' | 'saas' | 'selfhosted'
  api?: { post_knowledge_bases?: boolean }
}
```
New file:
```typescript
export type HealthResponse = {
  status: string
  deployment_mode?: 'saas' | 'selfhosted'
  api?: { post_knowledge_bases?: boolean }
}
```
Note: Remove `'dev'` from `deployment_mode` too since `deployment_mode: 'dev'` was removed from config (config.py shows `Literal["saas", "selfhosted"]`).

**auth-strategies.ts** — Remove:
- `showEnterpriseSso` function (not called from any live route)
- `showDirectoryLogin` function (not called from any live route)
- `hasAnyStrategy` function (not called from any live route — only in test)
- `gitlab` from `SOCIAL_LABELS` (gitlab provider was deleted from backend)
- `directory: false` in `DEFAULT_AUTH_CONFIG` — keep it for now (the `AuthConfig` type still has the field and `/v1/auth/config` still returns it). Just remove the dead functions.

After removal, `auth-strategies.ts` should only export:
- `SocialButton` interface
- `SOCIAL_LABELS` (without `gitlab`)
- `DEFAULT_AUTH_CONFIG`
- `socialLabel`
- `socialButtons`
- `showPasswordForm`

**auth-strategies.test.ts** — Remove tests for dead functions. Remove:
- Import of `hasAnyStrategy`, `showDirectoryLogin`, `showEnterpriseSso`
- Test `'undefined config falls back to defaults...'` — keep only the parts for `showPasswordForm` and `socialButtons`. Remove the `showEnterpriseSso(undefined)` and `showDirectoryLogin(undefined)` assertions.
- Test `'directory + enterprise toggles respected'` — remove entirely
- Test `'empty config (all off) reports no strategies'` — remove entirely (tests `hasAnyStrategy`)
- Keep the `gitlab` label test since `socialLabel` still has a fallback behavior — BUT remove the `gitlab` specific expected value since we're removing `gitlab` from `SOCIAL_LABELS`. Update the test assertion if needed.

- [ ] **Step 1: Update health-types.ts**

Edit `apps/frontend/src/lib/health-types.ts` to:
```typescript
/** GET /health JSON (fields may be absent on older API builds). */
export type HealthResponse = {
  status: string
  deployment_mode?: 'saas' | 'selfhosted'
  api?: { post_knowledge_bases?: boolean }
}
```

- [ ] **Step 2: Check HealthResponse callers for auth_mode**

```bash
cd apps/frontend && grep -rn "auth_mode" src --include="*.ts" --include="*.tsx"
```

Expected: zero hits after removing from type. If any component still reads `.auth_mode`, remove that UI code too.

- [ ] **Step 3: Update auth-strategies.ts — remove dead exports**

New content of `apps/frontend/src/lib/auth-strategies.ts`:
```typescript
/**
 * Pure helpers for adaptive auth UI.
 *
 * The login/signup pages render only the strategies the deployment enables,
 * driven by the public `GET /v1/auth/config` bootstrap. These helpers turn the
 * raw config into render decisions, with a safe default when the config has not
 * loaded yet (password-only, so the form is never blocked).
 */
import type { AuthConfig } from './admin-types'

export interface SocialButton {
  provider: string
  label: string
  startUrl: string
}

const SOCIAL_LABELS: Record<string, string> = {
  google: 'Google',
  github: 'GitHub',
}

export const DEFAULT_AUTH_CONFIG: AuthConfig = {
  password: true,
  social: [],
  directory: false,
  enterprise: true,
}

/** Label for a social provider key (falls back to a capitalized name). */
export function socialLabel(provider: string): string {
  return SOCIAL_LABELS[provider] ?? provider.charAt(0).toUpperCase() + provider.slice(1)
}

/** Build the ordered social buttons to render, with their start URLs. */
export function socialButtons(cfg: AuthConfig | undefined, apiBase = ''): SocialButton[] {
  const list = cfg?.social ?? []
  return list.map((provider) => ({
    provider,
    label: socialLabel(provider),
    startUrl: `${apiBase}/api/v1/auth/social/${provider}/start`,
  }))
}

/** Whether the password email/password form should render. */
export function showPasswordForm(cfg: AuthConfig | undefined): boolean {
  // Default to true when config absent so users are never locked out by a
  // failed bootstrap fetch.
  return cfg?.password ?? DEFAULT_AUTH_CONFIG.password
}
```

- [ ] **Step 4: Update auth-strategies.test.ts — remove dead test cases**

New content of `apps/frontend/src/lib/auth-strategies.test.ts`:
```typescript
/**
 * Run: `node --test --experimental-strip-types src/lib/auth-strategies.test.ts`
 * Pure logic, no React deps, no DOM.
 */
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import type { AuthConfig } from './admin-types.ts'
import {
  DEFAULT_AUTH_CONFIG,
  showPasswordForm,
  socialButtons,
  socialLabel,
} from './auth-strategies.ts'

const FULL: AuthConfig = {
  password: true,
  social: ['google', 'github'],
  directory: true,
  enterprise: true,
}

test('defaults keep password + enterprise on, social/directory off', () => {
  assert.equal(DEFAULT_AUTH_CONFIG.password, true)
  assert.equal(DEFAULT_AUTH_CONFIG.enterprise, true)
  assert.deepEqual(DEFAULT_AUTH_CONFIG.social, [])
  assert.equal(DEFAULT_AUTH_CONFIG.directory, false)
})

test('undefined config falls back to password on', () => {
  assert.equal(showPasswordForm(undefined), true)
  assert.deepEqual(socialButtons(undefined), [])
})

test('renders only configured social providers, in order', () => {
  const btns = socialButtons(FULL, 'http://api')
  assert.deepEqual(btns.map((b) => b.provider), ['google', 'github'])
  assert.equal(btns[0].startUrl, 'http://api/api/v1/auth/social/google/start')
  assert.equal(btns[0].label, 'Google')
})

test('password can be disabled', () => {
  const cfg: AuthConfig = { ...FULL, password: false }
  assert.equal(showPasswordForm(cfg), false)
})

test('socialLabel falls back to capitalized provider', () => {
  assert.equal(socialLabel('custom'), 'Custom')
})
```

- [ ] **Step 5: TypeScript check**

```bash
cd apps/frontend && pnpm exec tsc --noEmit
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add apps/frontend/src/lib/health-types.ts apps/frontend/src/lib/auth-strategies.ts apps/frontend/src/lib/auth-strategies.test.ts
git commit -m "chore(web): remove dead showEnterpriseSso/showDirectoryLogin/hasAnyStrategy, gitlab label, auth_mode type"
```

---

### Task 5: Fix stale comments in frontend files

**Files:**
- Modify: `apps/frontend/src/lib/authorizedFetch.ts`
- Modify: `apps/frontend/src/hooks/useMeQuery.ts`
- Modify: `apps/frontend/src/lib/rag-api.ts`
- Modify: `apps/frontend/src/vite-env.d.ts`

**authorizedFetch.ts line 16:** Change:
```
// Dev / CI fallback — no stored session yet (used when VITE_AUTH_MODE is absent or "dev").
```
To:
```
// Dev / CI fallback — no stored session yet (used in local dev without a seeded JWT).
```

Also update the JSDoc comment at top (lines 3–8):
Change:
```
 * Flow (single OIDC-consumer / token-bearer):
 *   1. If a stored access token exists → Bearer <token>
 *   2. Dev fallback: use VITE_DEV_BEARER_TOKEN / VITE_DEV_TOKEN / "devtoken"
```
To:
```
 * Flow (Bearer token):
 *   1. If a stored access token exists → Bearer <token>
 *   2. Dev / CI fallback: use VITE_DEV_BEARER_TOKEN / VITE_DEV_TOKEN / "devtoken"
```

**useMeQuery.ts line 8:** Change:
```typescript
/** MSAL + Bearer only run in the browser; skip during SSR. */
```
To:
```typescript
/** Bearer auth only runs in the browser; skip during SSR. */
```

**rag-api.ts:** Find and update the stale "shared bearer-from-MSAL header" comment. Change to "shared Bearer auth header".

**vite-env.d.ts line 6:** Remove the comment on `VITE_AUTH_MODE` — it still references `dev` auth mode. Update to:
```typescript
  /** Dev/CI override: skip stored JWT and send this token as Bearer instead. */
  readonly VITE_AUTH_MODE?: string
```

Or if `VITE_AUTH_MODE` is no longer actually read anywhere in the codebase (check first), remove it entirely.

- [ ] **Step 1: Check VITE_AUTH_MODE actual usage**

```bash
cd apps/frontend && grep -rn "VITE_AUTH_MODE" src --include="*.ts" --include="*.tsx"
```

Expected output from `authorizedFetch.ts`: line 16 comment only — no actual `import.meta.env.VITE_AUTH_MODE` usage in code logic. If that's the case, remove the `VITE_AUTH_MODE` type declaration from `vite-env.d.ts` entirely since no code reads it.

- [ ] **Step 2: Fix authorizedFetch.ts comments**

Edit `apps/frontend/src/lib/authorizedFetch.ts` lines 3–8 and 16 as described above.

- [ ] **Step 3: Fix useMeQuery.ts comment**

Edit `apps/frontend/src/hooks/useMeQuery.ts` line 8.

- [ ] **Step 4: Fix rag-api.ts comment**

Edit `apps/frontend/src/lib/rag-api.ts` — find the "MSAL" comment and replace with plain "Bearer auth".

- [ ] **Step 5: Fix vite-env.d.ts**

If `VITE_AUTH_MODE` has no code callers (confirmed in Step 1), remove that line from `vite-env.d.ts`.

- [ ] **Step 6: TypeScript check**

```bash
cd apps/frontend && pnpm exec tsc --noEmit
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add apps/frontend/src/lib/authorizedFetch.ts apps/frontend/src/hooks/useMeQuery.ts apps/frontend/src/lib/rag-api.ts apps/frontend/src/vite-env.d.ts
git commit -m "chore(web): update stale MSAL/auth_mode comments to reflect Bearer-only flow"
```

---

### Task 6: Backend — remove dead code in config/loader.py, rbac/catalog.py, middleware/setup_guard.py, auth/claims_provision.py, auth/limiter.py

**Files:**
- Modify: `server/api/src/ai_portal/auth/config/loader.py`
- Modify: `server/api/src/ai_portal/rbac/catalog.py`
- Modify: `server/api/src/ai_portal/core/middleware/setup_guard.py`
- Modify: `server/api/src/ai_portal/auth/claims_provision.py`
- Modify: `server/api/src/ai_portal/auth/limiter.py`
- Modify: `server/api/src/ai_portal/auth/idp/model.py` (stale comment only)

**loader.py:** Remove `gitlab` from `_SOCIAL_KNOWN`:
```python
# Before
_SOCIAL_KNOWN = ("google", "github", "gitlab")
# After
_SOCIAL_KNOWN = ("google", "github")
```

**rbac/catalog.py:** Remove `scim:read` and `scim:write` permission entries:
```python
# Remove these two lines:
Permission("scim:read", "Read SCIM endpoints", "control_plane"),
Permission("scim:write", "Configure SCIM endpoints", "control_plane"),
```

**setup_guard.py:** Remove `"/setup"` from `EXEMPT_PATHS`:
```python
# Before
EXEMPT_PATHS = {"/health", "/setup", "/auth/login"}
# After
EXEMPT_PATHS = {"/health", "/auth/login"}
```

**claims_provision.py:** Update the module docstring. Change:
```
Shared by social login and directory (LDAP/AD) bind.
```
To:
```
Shared by social login and enterprise SSO (OIDC).
```

**limiter.py:** Remove `mfa_verify_limiter` and its entry in `get_scoped_limiter`. Current code (lines 97, 106):
```python
mfa_verify_limiter = LoginLimiter()
...
"mfa_verify": mfa_verify_limiter,
```
After removal, `mfa_verify_limiter` and the `"mfa_verify"` mapping entry are gone.

Also update the comment above the scoped limiters section. Change:
```
# Each scope gets its own singleton so the buckets do not bleed across routes
# (e.g. a failed TOTP attempt must not lock the user out of /login).
```
To:
```
# Each scope gets its own singleton so the buckets do not bleed across routes.
```

**auth/idp/model.py line 58:** Update stale comment. Change:
```python
# Provider key in the registry — e.g. ``oidc``, ``saml``, ``entra``.
```
To:
```python
# Provider key in the registry — ``oidc`` for generic OIDC, ``google`` for Google Workspace.
```

- [ ] **Step 1: Edit loader.py — remove gitlab**

Edit `server/api/src/ai_portal/auth/config/loader.py` line 28:
```python
_SOCIAL_KNOWN = ("google", "github")
```

- [ ] **Step 2: Edit rbac/catalog.py — remove scim permissions**

Remove lines 53–54 from `server/api/src/ai_portal/rbac/catalog.py`:
```python
    Permission("scim:read", "Read SCIM endpoints", "control_plane"),
    Permission("scim:write", "Configure SCIM endpoints", "control_plane"),
```

- [ ] **Step 3: Edit setup_guard.py — remove /setup exempt path**

Edit `server/api/src/ai_portal/core/middleware/setup_guard.py` line 13:
```python
EXEMPT_PATHS = {"/health", "/auth/login"}
```

Also update the class docstring comment from:
```
"""Block all routes with 503 when DEPLOYMENT_MODE=selfhosted and no orgs exist."""
```
to (same — no change needed, this is fine).

- [ ] **Step 4: Edit claims_provision.py — update docstring**

Edit `server/api/src/ai_portal/auth/claims_provision.py` lines 5–6:

Old:
```python
Shared by social login and directory (LDAP/AD) bind. Given verified claims,
```
New:
```python
Shared by social login and enterprise SSO (OIDC). Given verified claims,
```

- [ ] **Step 5: Edit limiter.py — remove mfa_verify_limiter**

In `server/api/src/ai_portal/auth/limiter.py`:

Remove line 97: `mfa_verify_limiter = LoginLimiter()`

Remove line 106: `"mfa_verify": mfa_verify_limiter,`

Update the comment (lines 93–95) to remove TOTP reference:
```python
# Each scope gets its own singleton so the buckets do not bleed across routes.
```

- [ ] **Step 6: Edit idp/model.py — update stale comment**

Edit line 58 of `server/api/src/ai_portal/auth/idp/model.py`:
```python
    # Provider key in the registry — ``oidc`` for generic OIDC, ``google`` for Google Workspace.
```

- [ ] **Step 7: Verify backend imports cleanly**

```bash
cd server/api && PYTHONPATH=src DEPLOYMENT_MODE=saas SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx .venv/Scripts/python.exe -c "import ai_portal.main; print('OK')"
```

Expected: `OK` printed, no errors.

- [ ] **Step 8: Commit**

```bash
git add server/api/src/ai_portal/auth/config/loader.py
git add server/api/src/ai_portal/rbac/catalog.py
git add server/api/src/ai_portal/core/middleware/setup_guard.py
git add server/api/src/ai_portal/auth/claims_provision.py
git add server/api/src/ai_portal/auth/limiter.py
git add server/api/src/ai_portal/auth/idp/model.py
git commit -m "chore(api): remove dead scim perms, gitlab provider, /setup exempt path, mfa limiter + stale comments"
```

---

### Task 7: Full build verification and report generation

**Files:**
- Create: `.superpowers/sdd/task-deadcode-report.md`

- [ ] **Step 1: Run TypeScript type check**

```bash
cd apps/frontend && pnpm exec tsc --noEmit 2>&1
```

Expected: no errors.

- [ ] **Step 2: Run frontend build**

```bash
cd apps/frontend && pnpm build 2>&1
```

Expected: successful build with no errors. If there are TS errors, fix them (they indicate missed dead-code references).

- [ ] **Step 3: Verify backend import**

```bash
cd server/api && PYTHONPATH=src DEPLOYMENT_MODE=saas SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx .venv/Scripts/python.exe -c "import ai_portal.main; print('backend_ok')"
```

Expected: `backend_ok`.

- [ ] **Step 4: Verify routeTree has no dead routes**

```bash
grep -E "Scim|Directory|Sso" apps/frontend/src/routeTree.gen.ts
```

Expected: no output (all three routes removed).

- [ ] **Step 5: Write the report**

Create `.superpowers/sdd/task-deadcode-report.md` with:

```markdown
# Dead Auth Code Cleanup — Task Report

Generated: 2026-06-21

## Changes Table

| File | Action | Reason |
|---|---|---|
| `apps/frontend/src/routes/admin/sso.tsx` | DELETED | Calls `/v1/idp-connections` — not a live route |
| `apps/frontend/src/routes/admin/directory.tsx` | DELETED | Calls `/v1/ldap-connections` — not a live route |
| `apps/frontend/src/routes/admin/scim.tsx` | DELETED | Calls `/v1/scim/endpoints` — not a live route |
| `apps/frontend/src/routes/admin/route.tsx` | MODIFIED | Removed SSO/Directory/SCIM nav entries |
| `apps/frontend/src/routeTree.gen.ts` | REGENERATED | tsr generate after route deletions |
| `apps/frontend/src/lib/idp-config.ts` | DELETED | Only imported by deleted sso.tsx |
| `apps/frontend/src/lib/idp-config.test.ts` | DELETED | Tests deleted module |
| `apps/frontend/src/lib/scim-form.ts` | DELETED | Only imported by deleted scim.tsx |
| `apps/frontend/src/lib/scim-form.test.ts` | DELETED | Tests deleted module |
| `apps/frontend/src/lib/admin-types.ts` | MODIFIED | Removed IdpKind/IdpConnection, ScimPreset/ScimEndpoint*, LdapKind/LdapConnection* blocks |
| `apps/frontend/src/lib/admin-api.ts` | MODIFIED | Removed fetchIdpConnections/create/update/delete, all scim fns, all ldap fns |
| `apps/frontend/src/lib/health-types.ts` | MODIFIED | Removed `auth_mode?: 'dev' \| 'entra'` (field no longer returned) |
| `apps/frontend/src/lib/auth-strategies.ts` | MODIFIED | Removed showEnterpriseSso, showDirectoryLogin, hasAnyStrategy, gitlab label |
| `apps/frontend/src/lib/auth-strategies.test.ts` | MODIFIED | Removed tests for deleted functions |
| `apps/frontend/src/lib/authorizedFetch.ts` | MODIFIED | Stale MSAL/auth_mode comment updated |
| `apps/frontend/src/hooks/useMeQuery.ts` | MODIFIED | Stale MSAL comment updated |
| `apps/frontend/src/lib/rag-api.ts` | MODIFIED | Stale MSAL comment updated |
| `apps/frontend/src/vite-env.d.ts` | MODIFIED | Removed VITE_AUTH_MODE (no code reads it) |
| `server/api/src/ai_portal/auth/config/loader.py` | MODIFIED | Removed `gitlab` from _SOCIAL_KNOWN |
| `server/api/src/ai_portal/rbac/catalog.py` | MODIFIED | Removed scim:read, scim:write permissions |
| `server/api/src/ai_portal/core/middleware/setup_guard.py` | MODIFIED | Removed `/setup` from EXEMPT_PATHS |
| `server/api/src/ai_portal/auth/claims_provision.py` | MODIFIED | Updated stale docstring |
| `server/api/src/ai_portal/auth/limiter.py` | MODIFIED | Removed mfa_verify_limiter + mapping entry + TOTP comment |
| `server/api/src/ai_portal/auth/idp/model.py` | MODIFIED | Updated stale kind comment |

## Kept / Ambiguous — Not Removed

| Item | Reason kept |
|---|---|
| `auth/idp/model.py` + `idp_connections` table | OIDC SSO uses it; `/v1/auth/sso/start` resolves IdP connections |
| `AuthConfig.directory` field in `admin-types.ts` + `auth-strategies.ts` DEFAULT | Backend still returns `directory` from `/v1/auth/config` even if no LDAP backend exists; removing would break type shape |
| `auth/strategies/dev.py` | `UserManager` is used by live auth routes (jwt, portal_keys) |
| `VITE_DEV_BEARER_TOKEN` / `VITE_DEV_TOKEN` in vite-env.d.ts | Still actually read by `authorizedFetch.ts` for dev/CI |
| `idp:read` / `idp:write` in rbac/catalog.py | OIDC SSO connections still use the idp_connections table; keeping these is correct |
| `sso_callback_limiter` in limiter.py | Live — used by `routes_sso.py` |
| `password_reset_limiter` in limiter.py | Live — may be used by password reset route |
| `auth/config/loader.py` `directory_enabled` / `enterprise_enabled` flags | Live — returned by `/v1/auth/config` |

## Build Results

- `pnpm exec tsc --noEmit`: [PASS/FAIL — fill in]
- `pnpm build`: [PASS/FAIL — fill in]
- `import ai_portal.main`: [PASS/FAIL — fill in]
- routeTree.gen.ts: no Scim/Directory/Sso route references: [PASS/FAIL — fill in]
```

- [ ] **Step 6: Final commit**

```bash
git add .superpowers/sdd/task-deadcode-report.md
git commit -m "chore: add dead auth code cleanup report"
```
