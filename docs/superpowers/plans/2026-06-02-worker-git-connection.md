# Worker Git Connection — Implementation Plan (Plan 2)

> **For agentic workers:** Implement task-by-task (subagent-driven). Steps use `- [ ]`.

**Goal:** Let users connect GitHub via an access token (personal or org), pick which repos workers may use, and replace the spawn dialog's hardcoded GitLab fields + the disabled Integrations "Configure" button with the real connect-first workflow.

**Architecture:** Extend the existing `git_integrations` model + a new `git_repos` table. A connection service validates a pasted GitHub token (`GET /user`) and lists repos (`GET /user/repos`) using the existing `GitHubProvider` httpx pattern, encrypting the token via `core/crypto/envelope.py`. Control-plane endpoints under `/v1/workers/git-integrations`. Frontend: real Connect flow on `workers/integrations.tsx` + a repo picker / connect-first guard in the spawn dialog.

**Spec:** `docs/superpowers/specs/2026-06-02-worker-creation-git-connection-design.md` §3, §4.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + httpx (backend), React + TanStack Query + shared `~/components/ui/select` (frontend), Playwright (E2E mock-server).

---

## Task 1 — DB: extend `git_integrations` + `git_repos` table + migration
- Modify `server/api/src/ai_portal/workers/model.py`: on `GitIntegration` add `user_id` (nullable FK → users), `account_login` (String, nullable), `auth_type` (String(16), default `'token'`). Add a new `GitRepo` model → table `git_repos` (`id` uuid, `integration_id` FK → git_integrations ON DELETE CASCADE, `full_name` String, `default_branch` String default `'main'`, `enabled` Boolean default False, `created_at`).
- Alembic migration `074_worker_git_repos` (down_revision `073_catalog_usable_in_worker`): add the 3 columns to `git_integrations`, create `git_repos`.
- Test (`tests/workers/test_git_models.py`): assert new columns exist + `GitRepo.__table__` columns. TDD.

## Task 2 — Connection service (validate + list repos)
- Create `server/api/src/ai_portal/workers/git/connection_service.py`: `connect_github(db, *, owner_user_id|org_id, token) -> (integration, repos)` — validate via `GET https://api.github.com/user` (Bearer token, httpx), store `account_login`, encrypt token with `core/crypto/envelope.py` into `config_encrypted`, list repos via `GET /user/repos?per_page=100`, upsert `git_repos` (enabled defaults False). Plus `list_integrations`, `list_repos`, `set_repo_enabled`, `delete_integration`, `decrypt_token`.
- Test (`tests/workers/test_git_connection_service.py`): use `respx`/monkeypatched httpx (NO real GitHub) to stub `/user` + `/user/repos`; assert account_login stored, token round-trips through envelope crypto, repos upserted. TDD.

## Task 3 — Endpoints `/v1/workers/git-integrations`
- Create `server/api/src/ai_portal/workers/git/router.py` (mount in `main.py`): `POST` (`{kind:'github', scope:'user'|'org', token}`→connect), `GET` (list, no secrets), `DELETE /{id}`, `GET /{id}/repos`, `PATCH /{id}/repos` (`{enabled_full_names: string[]}`). Pydantic schemas in `workers/git/schemas.py`. Never return the token.
- Test (`tests/workers/test_git_router.py`): stubbed httpx; POST connect → 201 with account + repos; GET list; PATCH repos toggles enabled. TDD.

## Task 4 — Frontend: real Connect flow on Integrations page
- Rewrite `apps/frontend/src/routes/workers/integrations.tsx` GitHub card: "Connect" opens a token input + My-account/Org toggle (`<Select>`); on submit POST `/v1/workers/git-integrations`; show connected state (`@login`) + repo list with enable checkboxes (PATCH on toggle). Add `apps/frontend/src/lib/git-integrations-api.ts` (typed fetchers) + `useGitIntegrationsQuery`. Keep other provider cards as "coming soon" disabled (no fake).
- `tsc --noEmit` clean.

## Task 5 — Spawn dialog: repo picker + connect-first
- Modify `apps/frontend/src/routes/workers/instances.tsx` `SpawnDrawer`: replace the GitLab project / Repo URL / Branch fields with a **Repository** `<Select>` populated from enabled repos (via a `useEnabledReposQuery` over `/v1/workers/git-integrations` + repos). If none enabled → render a callout "No Git provider connected — Connect in Settings →" linking to `/workers/integrations`, and disable Spawn. Send `repo: { integration_id, full_name, branch }` (or keep `repo_url` derived from the picked repo's clone URL) in the spawn body; drop the gitlab connector hardcode. `tsc --noEmit` clean.
- E2E (`e2e/workers/spawn-repo-picker.spec.ts` + mock-server git-integrations handlers): empty state shows connect-first + Spawn disabled; with a mocked enabled repo, the picker shows it and Spawn enables.

## Self-Review
- Spec coverage: §3 connection (T1–T4), §4 connect-first redirect (T5). Token never leaves the server (T2/T3). user-XOR-org owner (T1).
- Follow-ups: GitHub App (`auth_type='app'`), GitLab/others, triggers — future.
