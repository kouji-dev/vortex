# Worker Creation & Git Connection UX — Design

- **Date:** 2026-06-02
- **Status:** Approved (brainstorm), pending implementation plan
- **Refines:** `docs/superpowers/specs/2026-05-28-task-workers-design.md` (Worker Model & Runtime; Git Integration). This spec details the *creation* and *connection* UX only; it does not change the orchestrator/runtime architecture defined there.

## Motivation

The current Spawn-a-worker flow (`apps/frontend/src/routes/workers/instances.tsx` → `SpawnDrawer`) is a stand-in:

- **Model** is a free-text input (`claude-sonnet-4-6`) — no validation, no discoverability.
- The agent runtime is a separate "Agent SDK" select (`Claude Agent SDK` / `Codex CLI`).
- There is **no thinking-effort control**.
- Git is **hardcoded** to a GitLab connector with free-text `repo_url` / `project` / `branch`; `workers/integrations.tsx` is a placeholder.

This redesign makes worker creation catalog-driven and gives users real model + effort choices, and replaces the hardcoded git fields with a token-based GitHub connection that supports both an individual user and an organization, plus multiple repositories.

## Scope

**In scope**

1. A catalog flag controlling which models appear in the worker picker.
2. Worker creation: **Model** select + **Effort** select (runtime inferred from the model).
3. Git connection via **access token** (GitHub first), owned by a **user** or an **org**, with multi-repo selection.
4. A "connect-first" guard: spawning a worker with no usable repo deep-links to Settings to connect, then returns.
5. Wiring the existing **execution-provider (sandbox) layer** so the local/dev/E2E default is **Docker** and `fake` is retired from runtime paths.

**Out of scope (future — design seams only)**

- GitHub **App** bot identity (autonomous PR/issue comments).
- Pluggable task **triggers** (issue comment `/worker …`, PR comments, schedules).
- **Multi-platform bot** (Discord/Slack) — "Vortex anywhere".

The data model and APIs below leave explicit room for these (e.g. `auth_type`, owner polymorphism) so they are additive, not rewrites.

## 1. Catalog flag — `usable_in_worker`

- Add `usable_in_worker: bool` (default `false`) to `catalog_models` (`server/api/src/ai_portal/catalog/model.py`) via Alembic migration.
- Seed: set `true` for Claude (Opus/Sonnet/Haiku) and GPT‑5 Codex rows; leave `false` for chat-only / Gemini rows the agent CLIs can't drive.
- Admin can toggle it from the catalog/models admin surface (same place `is_active` / `requires_entitlement` are managed).
- Worker model picker fetches catalog rows filtered by `usable_in_worker AND is_active` (and entitlement rules already applied to the catalog).

## 2. Model + Effort selection

The `SpawnDrawer` form fields become:

| Field | Control | Source |
|---|---|---|
| Name | text input | — |
| **Model** | `<Select>` (shared `components/ui/select`) | catalog rows where `usable_in_worker` |
| **Effort** | `<Select>` | `Low / Medium / High / Max` |
| Mode | `<Select>` | `interactive` / `autonomous` (unchanged) |
| Repository | repo picker (see §4) | enabled repos of a git connection |

- **Runtime is inferred** from the selected model's provider: Anthropic → `claude` (Claude Agent SDK), OpenAI Codex → `codex` (Codex CLI). The standalone runtime select is removed. `WorkerRuntime` stays `'claude' | 'codex'`.
- **Effort** defaults to the catalog row's existing `effort` value and offers the levels the model supports (a model with no high-reasoning tier won't offer `Max`). Effort is forwarded to the agent runtime / gateway as the reasoning-effort hint (exact per-provider parameter verified at implementation, per the no-stale-model-knowledge rule).
- `spawnWorker` request body (`POST /v1/workers/instances`) gains `model` (catalog slug or api_model_id), `effort`, and a repo reference (see §4); `runtime` may be sent or derived server-side.

## 3. Git connection — token-first, user or org

Extends the existing `git_integrations` model (`server/api/src/ai_portal/workers/model.py`) rather than adding a parallel table.

**`git_integrations` (extended)**

- Existing: `id`, `org_id`, `kind` (provider, e.g. `github`), `config_encrypted` (LargeBinary, envelope-encrypted via the same crypto as `provider_credentials`), `enabled`.
- Add: `user_id` (nullable FK to `users`) — **owner is `user_id` XOR `org_id`**. A personal connection powers that user's workers; an org connection (admin-created) is shared across members.
- Add: `account_login` (plaintext, for display, e.g. `@octocat`), `auth_type` (`'token'` now; `'app'` reserved).
- `config_encrypted` stores the token (and any provider config). Never returned to the client.

**`git_repos` (new)**

- `id`, `integration_id` (FK → `git_integrations`), `full_name` (`octocat/web-app`), `default_branch`, `enabled` (bool), `created_at`.
- Populated by listing repos accessible to the token on connect; the user toggles `enabled` per repo.

**Settings flow** (Workers → Integrations / Settings, replacing the placeholder):

1. Choose **Connect as → My account / Organization** (org option gated to admins).
2. Paste a **GitHub access token** (fine-grained PAT with repo + contents access preferred; classic token accepted).
3. **Connect** → server validates the token, stores it encrypted, records `account_login`, and lists accessible repos.
4. User checks the **repositories enabled for workers** (multi-select).

GitLab/others follow the same shape later (different `kind`, same token model).

## 4. Connect-first redirect

- The Repository field in `SpawnDrawer` is a picker over **enabled repos** across the actor's usable connections (their personal one + any org one).
- If there are **no enabled repos / no connection**, the field renders a callout — "No Git provider connected — Connect in Settings →" — that **blocks Spawn** and deep-links to the Settings page (§3). On return, the picker is populated and the previously-entered form state is preserved.
- The same guard is reused anywhere a worker/task requires a repo.

## 5. Execution provider (sandbox) layer

**Already exists — reuse, do not rebuild.** `server/api/src/ai_portal/workers/sandboxes/protocol.py` defines the `SandboxProvider` Protocol (`provision` / `exec` / `stream_exec`, `SandboxHandle`); concrete providers live in `workers/sandboxes/providers/` (`docker`, `kubernetes`, `e2b`, `daytona`, `firecracker`, `fake`). The orchestrator talks only to `SandboxProvider`, never a provider-specific API.

- **Provider is chosen per pool/template**, not per task: `sandbox_provider` is a column on the worker/pool model and `WorkerCreate.sandbox_provider` defaults to `"docker"`. The spawn form inherits the pool's provider; admins set it on the pool template.
- **Local / dev / E2E → `docker`** (the existing default). `DockerSandbox` runs a container via the Docker SDK with `mem_limit` / `nano_cpus` / `pids_limit` and restricted egress; requires the Docker daemon. **Prod → `kubernetes`** (gVisor/Kata isolation).
- **`fake` is test-only** and must never be a runtime default (global no-fake directive). Local testing of the real execution path uses `docker`.
- **Spawn provisioning flow:** orchestrator → `sandboxes.registry.get(pool.sandbox_provider).provision(...)` → container/pod → clone the selected repo (§4) using the git-connection token (§3) → inject `ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL` pointing at the gateway → launch the chosen agent CLI (runtime inferred from the model, §2) with the model + effort, brokered by `workers/agent_runtime/in_sandbox_runner.py`.
- **Hard dependency:** actual model calls remain blocked on the gateway real-provider adapters (per the task-workers spec). The Docker sandbox can provision and launch the agent CLI today, but the CLI's LLM calls only succeed once the gateway path is real.

## API surface (control-plane, `/v1/workers/...`)

- `GET /v1/workers/git-integrations` — list the actor's usable connections (no secrets).
- `POST /v1/workers/git-integrations` — `{ kind, scope: 'user'|'org', token }` → validate, encrypt, return connection + discovered repos.
- `DELETE /v1/workers/git-integrations/{id}` — remove a connection.
- `GET /v1/workers/git-integrations/{id}/repos` — list discovered repos with `enabled`.
- `PATCH /v1/workers/git-integrations/{id}/repos` — set the enabled set.
- `GET /v1/catalog/models?usable_in_worker=true` (or a worker-scoped variant) — model picker source.
- `POST /v1/workers/instances` — extended body: `{ name, model, effort, mode, repo: { integration_id, full_name, branch } }`.

## Testing

- **E2E (Playwright, mock-server):** spawn form shows Model + Effort selects sourced from a worker-flagged catalog; Repository empty-state shows "Connect in Settings" and blocks Spawn; after a mocked connection + repo-enable, the picker populates and Spawn enables. Git settings: connect (mocked token validation) → repo list → toggle enabled. All via the shared mock-server + `page.route`, no real GitHub calls.
- **Unit/backend:** token encryption round-trip; owner = user XOR org constraint; repo enable/disable; catalog filter by `usable_in_worker`.
- **Sandbox/integration:** worker provisioning runs against the real `docker` provider (Docker daemon required) — provision → clone a repo → exec a command → teardown; assert mem/cpu/pids limits applied. `fake` is used only in pure unit tests that can't reach a Docker daemon, never as a runtime default.

## Migrations

1. `catalog_models.usable_in_worker` (default false) + seed update.
2. `git_integrations`: add `user_id` (nullable), `account_login`, `auth_type` (default `'token'`).
3. `git_repos` table.

## Decisions & open details

- **Runtime inference** map (provider → runtime) lives server-side and in `workers-types`; a model whose provider has no agent CLI is simply never `usable_in_worker`.
- **Effort → provider parameter** mapping (Anthropic extended-thinking vs OpenAI `reasoning_effort`) is resolved at the gateway and verified against current provider APIs at implementation time.
- **Token validation** uses the provider's lightweight identity + repo-list endpoints; details pinned at implementation.
- Personal vs org **precedence** when both exist: the spawn form lets the user choose which connection/repo; no implicit precedence.
