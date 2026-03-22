# Microsoft Entra authentication & RBAC — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace dev-only bearer auth with optional **Microsoft Entra JWT** validation, **user upsert** from token claims, **`roles`-based RBAC** dependencies, and a **frontend sign-in** path (**MSAL**, **all product routes protected**) that sends access tokens to the API; keep **`auth_mode=dev`** for CI and local workflows.

**Architecture:** Single-tenant Entra: SPA (PKCE) acquires API-scoped access tokens; FastAPI validates JWTs against tenant JWKS, maps `oid` → `users` row, exposes `GET /api/me`; coarse permissions from token `roles` claim; resource routes continue to rely on `user_id` ownership. See spec: `docs/superpowers/specs/2026-03-22-auth-entra-design.md`.

**Tech stack:** FastAPI, Pydantic Settings, PyJWT (or equivalent) + JWKS fetch/cache, PostgreSQL/SQLAlchemy, TanStack Router, `@azure/msal-browser` + `@azure/msal-react` (or `@azure/msal-react` with React 19 — verify compatibility in Task 1).

---

## File map (planned)

| Area | Create | Modify |
|------|--------|--------|
| Settings | — | `backend/src/ai_portal/config.py` |
| JWT / Entra | `backend/src/ai_portal/auth/entra.py` (validate + claims) | — |
| User upsert | `backend/src/ai_portal/services/user_identity.py` (name TBD) | — |
| Deps | — | `backend/src/ai_portal/api/deps.py` |
| Me route | `backend/src/ai_portal/api/me.py` | `backend/src/ai_portal/main.py` |
| Models / DB | — | `backend/src/ai_portal/models/user.py`, new Alembic revision under `backend/alembic/versions/` |
| Tests | `backend/tests/test_auth_entra.py`, extend existing API tests | `backend/tests/conftest.py` if shared fixtures needed |
| Frontend auth | `frontend/src/auth/msalConfig.ts`, `frontend/src/auth/AuthProvider.tsx`, `frontend/src/lib/api.ts` (or similar) | `frontend/package.json`, `frontend/src/router.tsx`, `frontend/src/routes/__root.tsx` |
| Azure API client (follow-on) | `backend/src/ai_portal/integrations/azure_graph.py` (or `services/msal_confidential.py`) | `backend/src/ai_portal/config.py`, `backend/pyproject.toml` (`msal`) |
| Docs | `docs/superpowers/specs/` (already has design) | Optional `README` snippet for env vars |

---

### Task 1: Dependencies and Entra env surface

**Files:**

- Modify: `backend/pyproject.toml` (add `pyjwt[crypto]` or `python-jose` + `httpx` — pick one stack and use consistently)
- Modify: `backend/src/ai_portal/config.py`

- [ ] **Step 1:** Add settings fields: `auth_mode: Literal["dev", "entra"] = "dev"`, `entra_tenant_id: str = ""`, `entra_api_audience: str = ""` (API identifier URI or app id as required by validation), optional `entra_issuer: str | None = None` (default construct from tenant).
- [ ] **Step 2:** When `auth_mode == "entra"`, document that `entra_tenant_id` and `entra_api_audience` are required at runtime (fail fast in dependency or lifespan if missing).
- [ ] **Step 3:** Run `ruff check src tests` from `backend/`.

---

### Task 2: User model — stable Entra link

**Files:**

- Modify: `backend/src/ai_portal/models/user.py`
- Create: `backend/alembic/versions/00X_user_entra_object_id.py` (next revision after existing chain)

- [ ] **Step 1:** Add nullable **`entra_object_id`** column, **unique constraint** where not null (PostgreSQL partial unique index is ideal).
- [ ] **Step 2:** Run `alembic upgrade head` against local Postgres.
- [ ] **Step 3:** Run `ruff check src tests`, `pytest`.

---

### Task 3: JWT validation module

**Files:**

- Create: `backend/src/ai_portal/auth/__init__.py`
- Create: `backend/src/ai_portal/auth/entra.py`

- [ ] **Step 1:** Implement JWKS URL for tenant v2 metadata, cache keys with TTL (in-memory is enough for MVP).
- [ ] **Step 2:** Validate: signature algorithm, `aud` (accept API audience), `iss` / tenant, `exp`, and **`tid` == `entra_tenant_id`**.
- [ ] **Step 3:** Return decoded claims dict; extract `oid`, `roles` (list), email from standard/upn/preferred_username claims.
- [ ] **Step 4:** Unit tests with a **locally signed JWT** using a test RSA key injected as JWKS override (avoid live Entra in CI) — add `backend/tests/test_auth_entra.py`.

---

### Task 4: User upsert from claims

**Files:**

- Create: `backend/src/ai_portal/services/user_identity.py`

- [ ] **Step 1:** Given claims + `Session`, find user by `entra_object_id == oid` if present; else match by **normalized email** if claim present; else create row.
- [ ] **Step 2:** Update `email` on existing row if claim changes (optional but useful).
- [ ] **Step 3:** Tests: upsert creates once, second call returns same `id`.

---

### Task 5: `get_current_user` — branch on `auth_mode`

**Files:**

- Modify: `backend/src/ai_portal/api/deps.py`

- [ ] **Step 1:** If `auth_mode == "dev"`, keep current bearer + `dev_seed_user_email` behavior.
- [ ] **Step 2:** If `auth_mode == "entra"`, parse Bearer token, call validator, call upsert, return `User`.
- [ ] **Step 3:** Introduce a small **`Principal`** or attach **`token_roles: list[str]`** via `ContextVar` or extend return type — prefer a dedicated **`get_current_principal`** dependency that returns `(User, roles)` to avoid overloading `User` model. **Recommendation:** new type `CurrentUserCtx` dataclass used by routers that need roles; **`get_current_user`** returns only `User` for backward compatibility, with optional **`get_token_roles`** dependency reading from same request state.
- [ ] **Step 4:** Run `pytest` including existing `test_chat_api.py` / assistants tests under **dev mode** (ensure default env unchanged).

---

### Task 6: RBAC dependency

**Files:**

- Create: `backend/src/ai_portal/api/rbac.py` (or inside `deps.py` if tiny)
- Modify: one admin-only or test route to prove pattern (optional stub route under `me.py`)

- [ ] **Step 1:** `require_app_roles(*allowed: str)` FastAPI dependency: compares **intersection** of token `roles` with `allowed`; else `403`.
- [ ] **Step 2:** Test: token without role → 403; with role → 200.

---

### Task 7: `GET /api/me`

**Files:**

- Create: `backend/src/ai_portal/api/me.py`
- Modify: `backend/src/ai_portal/main.py`

- [ ] **Step 1:** Router prefix `/api`, tag `me`; response schema: `id`, `email`, `roles: list[str]`.
- [ ] **Step 2:** Register router in `main.py`.
- [ ] **Step 3:** Test with dev mode (roles empty or synthetic) and entra test JWT.

---

### Task 8: Frontend — MSAL and API client

**Files:**

- Modify: `frontend/package.json`
- Create: `frontend/src/auth/msalConfig.ts`, `frontend/src/auth/AuthProvider.tsx`
- Create: `frontend/src/lib/apiClient.ts` (wrap `redaxios` or `fetch` with token acquisition)

- [ ] **Step 1:** Add MSAL packages; env vars: `VITE_ENTRA_CLIENT_ID`, `VITE_ENTRA_TENANT_ID`, `VITE_ENTRA_API_SCOPE` (full scope string e.g. `api://xxx/access_as_user`).
- [ ] **Step 2:** Wrap app with `MsalProvider` in `frontend/src/router.tsx` or `__root.tsx`.
- [ ] **Step 3:** Implement `acquireApiAccessToken()` using silent acquire with redirect fallback.
- [ ] **Step 4:** `npm run build` from `frontend/`.

---

### Task 9: Frontend — protected shell

**Files:**

- Modify: `frontend/src/routes/__root.tsx` or add `frontend/src/routes/app.route.tsx` + children for future `/app/chat`

- [ ] **Step 1:** Public route `/` or `/login` triggers `loginRedirect` if unauthenticated.
- [ ] **Step 2:** After login, land on a minimal **authenticated home** (e.g. `/app`) that calls `GET /api/me` to verify token pipeline.
- [ ] **Step 3:** Handle 401 from API: clear cache / redirect to login.

---

### Task 10: Documentation for operators

**Files:**

- Modify: `README.md` at repo root **or** `backend/README.md` — only if an existing doc already describes env vars; otherwise add a short **“Entra setup”** subsection (minimal bullet list: app registrations, env vars for backend + frontend).

- [ ] **Step 1:** List all required environment variables for `auth_mode=entra` (backend + frontend).
- [ ] **Step 2:** Link to design spec path.

---

### Task 11: Verification (CI parity)

- [ ] From `backend/`: `ruff check src tests`, `pytest`.
- [ ] From `frontend/`: `npm run build`.
- [ ] Confirm default **`auth_mode` dev** keeps current developer workflow without Entra secrets.

---

### Task 12 (follow-on): Backend credentials for Azure APIs (Graph / ARM / etc.)

**When:** First feature that calls **Microsoft Graph** or another Entra-protected Azure API **as the signed-in user** or **as the app**.

**Files (illustrative):**

- Create: small wrapper using **`msal`** ConfidentialClientApplication on the API
- Modify: `backend/src/ai_portal/config.py` — e.g. `entra_api_client_secret` (dev) or thumbprint for cert; prefer **managed identity** + **DefaultAzureCredential** when deployed to Azure for **Azure resource** APIs (not a substitute for all Graph scenarios)

- [ ] **Step 1:** **User-delegated Graph:** register **delegated** Graph permissions on the **API** app; implement **OBO** — `acquire_token_on_behalf_of` with the incoming user access token assertion; cache Graph tokens per user/subject in memory with TTL.
- [ ] **Step 2:** **App-only (cron / queues):** separate **worker** app registration with **application** permissions + admin consent; **client credentials** (cert/secret or managed identity where supported). **Do not** rely on user **refresh tokens** or **`offline_access`** — acquire access tokens on demand, cache in memory until `exp`.
- [ ] **Step 3:** Document required Entra permissions and env vars next to Task 10 operator docs (interactive API app vs worker app).

See spec section **Backend → Microsoft Azure APIs**.

---

## Plan review

After implementation, use **superpowers:requesting-code-review** or human review for security-sensitive JWT and CORS/credential settings.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-03-22-auth-entra.md`. Two execution options:

1. **Subagent-driven (recommended)** — fresh subagent per task, review between tasks.  
2. **Inline execution** — execute tasks in this session with checkpoints.

Which approach do you want?
