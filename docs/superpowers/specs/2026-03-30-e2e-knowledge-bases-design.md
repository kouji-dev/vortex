# E2E testing: knowledge bases & chat (requirements validation)

**Date:** 2026-03-30  
**Status:** Approved (product intent)  
**Scope:** Playwright-based end-to-end tests against a real API and Postgres, using dev auth bypass. Initial scenarios cover the KBs area and chat KB attachment; the same harness is the default place to add E2E for future features so acceptance criteria stay verifiable **on the developer machine** (local-only for now).

---

## Problem

The frontend today has no browser E2E suite. Knowledge-base flows (list, create, upload) and chat KB attachment are multi-step and cross API boundaries. Relying only on unit/API tests risks regressions in wiring, UX, and async behavior (e.g. document ingest). We need a repeatable way to **validate requirements** when shipping new features, not only a one-off manual check.

---

## Goals

1. **Local:** Developers run E2E against an isolated Postgres instance (`local-e2e` Docker Compose) so dev data is never touched.
2. **Auth:** No Microsoft Entra in the E2E path; use existing **`AUTH_MODE=dev`** on the API and **`VITE_AUTH_MODE=dev`** with matching **`VITE_DEV_BEARER_TOKEN`** / **`DEV_BEARER_TOKEN`**.
3. **Coverage (first slice):**
   - **KBs page:** list → create KB (dialog) → open detail → **upload a file** → assert the document appears in the UI; poll until ingest-related status is stable if the UI exposes it (avoid flaky single-shot assertions).
   - **Chat:** open or create a conversation → open KB panel → toggle KB(s) → **save** → assert persisted attachment (reload or visible state / network not required if UI reflects server truth).
4. **Extensibility:** New features ship with E2E cases here when the feature is user-visible and requirement-critical; keep selectors stable via a **small, intentional set** of `data-testid` attributes where needed.
5. **Local-only execution:** E2E is not required to run in GitHub Actions or any remote CI in this phase; documentation and scripts target **local** runs only.

---

## Non-goals (this spec)

- Replacing backend `pytest` coverage for API contracts.
- Testing Entra login flows in E2E (out of scope while using dev auth).
- Full connector sync against real GitHub/GitLab/Confluence/S3 (orchestration may remain stubbed); file upload + **files** connector path is in scope.
- **GitHub Actions / shared CI** for Playwright (explicitly deferred; may be added later without changing the core harness).

---

## Architecture

### Isolated database (`local-e2e`)

- Add **`docker-compose.e2e.yml`** (or equivalent) with Compose **project name `local-e2e`** so networks/volumes are namespaced separately from `local-dev`.
- **Single required service:** Postgres **`pgvector/pgvector:pg17`**, database name **`ai_portal_e2e`**, credentials and `DATABASE_URL` example documented in repo for local use.
- **Host port:** bind to `127.0.0.1` on a port **distinct** from `5434` (used by `local-dev`) to avoid collisions.
- **Volume:** dedicated named volume for E2E only — do not reuse `ai-portal-db-data` from `local-dev`.
- **Redis:** optional in the same file for parity with root `docker-compose.yml`; the current backend codebase does not require Redis for KB upload/ingest paths. Include Redis in `local-e2e` only when an API or worker actually depends on it.

### Application processes

- **Backend:** run on the host, `DATABASE_URL` pointing at `ai_portal_e2e`, `alembic upgrade head` before tests, `AUTH_MODE=dev`, `DEV_BEARER_TOKEN`, `DEV_SEED_USER_EMAIL`, `UPLOAD_DIR` set to a writable directory (temp or project `.e2e-uploads` gitignored).
- **Frontend:** Vite dev server or `vite preview` with `VITE_API_URL` pointing at the E2E API and `VITE_AUTH_MODE=dev` plus matching bearer token env vars.

### Playwright

- Add Playwright as a **frontend devDependency**.
- **`baseURL`:** the frontend origin used for the run (typically `http://127.0.0.1:5173`).
- **Global setup:** wait for API readiness (e.g. health endpoint); ensure DB is migrated; optional one-time seed if the app requires data beyond dev seed user behavior.
- **Fixtures:** commit a **small** binary-safe test file (e.g. `.txt` or `.pdf`) under `frontend/e2e/fixtures/` for upload scenarios.
- **Flake control:** use explicit timeouts and **polling** for document ingest status when the API processes uploads asynchronously (`BackgroundTasks` / ingest pipeline).

### External services (LLM / embeddings)

- If ingest requires live API keys and local E2E becomes unstable, the implementation plan must choose one explicit strategy for **local** runs: **developer-provided keys** in `.env` (not committed), **no-network mocks** at the application boundary for E2E only, or **skipping ingest completion** and asserting only “upload accepted + row created” — pick one and document it in the E2E README. This spec does not mandate which until implementation discovers current ingest behavior with empty keys.

---

## Test scenarios (minimum for first local harness)

| ID | Scenario | Success criteria |
|----|----------|------------------|
| E2E-KB-1 | KB list and create | From `/knowledge-bases`, open create dialog, submit valid name/description, land on list or detail with new KB visible |
| E2E-KB-2 | File upload | On KB detail, upload fixture file; document row appears; if status shown, poll until terminal or timeout with clear failure message |
| E2E-CHAT-1 | Attach KBs to conversation | In chat UI, open KB panel, toggle at least one KB, save, re-open or refresh and selection matches |

Additional scenarios for new features are added under the same `frontend/e2e/` tree. If CI is introduced later, parallel sharding can be layered on without changing scenario IDs.

---

## Selector and maintainability rules

- Prefer role-based and accessible names from Playwright (`getByRole`, `getByLabel`).
- Add **`data-testid`** only for elements that are otherwise ambiguous or unstable (primary actions: create submit, file input, save on KB panel).
- Do not scatter test IDs across the entire app; justify each in PR review.

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Async ingest | Poll UI or API; generous timeout; assert intermediate “uploaded” if “embedded” is non-deterministic without keys |
| Dev auth accidentally enabled in production | Local E2E uses dev auth by convention; production uses `AUTH_MODE=entra`; no E2E-specific bypass in prod builds |
| Port collisions with `local-dev` | Fixed host port for E2E Postgres + documented in compose and README |

---

## Deliverables (implementation plan input)

1. `docker-compose.e2e.yml` (or agreed filename) with `name: local-e2e` and isolated Postgres (+ optional Redis).
2. Documented commands (e.g. README under `frontend/e2e/` or root): start DB, migrate, run API + web, install Playwright browsers once, run `npm run test:e2e`.
3. Playwright config + `frontend/e2e/` specs implementing the minimum scenarios above.
4. Small set of `data-testid` / accessibility fixes in KB and chat components as required for stable tests.

---

## Related documents

- `docs/superpowers/specs/2026-03-22-auth-entra-design.md` — production auth; E2E uses dev mode only.
- Root `docker-compose.yml` — reference for pgvector image and port collision avoidance.
