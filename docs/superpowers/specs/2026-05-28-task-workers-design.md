# Task Workers — Design Spec

## Purpose

- [ ] Autonomous AI coding agents that take a task, work in an isolated VM/container connected to git, and open a reviewable PR
- [ ] Triggered from chat, from Jira/Linear/Github issues, from PR comments, or scheduled
- [ ] Live-streamed to the browser so humans can watch and intervene
- [ ] Governed by the same Control Plane (audit, RBAC, budget, guardrails) as the rest of the suite
- [ ] Buyer: CTO / Head of Engineering / Eng Productivity Lead
- [ ] Comparable to: Devin, Cursor Background Agents, Cognition, Sweep, OpenHands

## Worker Model & Runtime (v1 — current direction)

> Refines the task-centric framing below. A **worker** is a first-class, persistent entity — not just a per-run sandbox. **A worker IS a task**: creating a worker (with its config) defines the task. The task-centric sections further down are legacy framing being reconciled into this model.

- [ ] **Worker = first-class entity**, listed on `/workers` with a lifecycle state: `idle` → `running` → `error` (+ `provisioning`, `stopped`)
- [ ] **Worker ↔ VM is 1:1 for v1** (multiple workers per VM deferred). The VM/sandbox **stays allocated to the worker** across task completion — NOT destroyed after each task; released only when the worker is stopped (`idle` = VM up, no active task)
- [ ] **Create a worker = define the task.** Config = `{model, mode, connector}` — `mode` is `interactive` (user chats live) or `autonomous` (works on its own from a trigger). Start connector = **GitLab repo** (the "vortex bot" is granted repo access). On create → provision VM → clone repo → launch the coding agent
- [ ] **Gateway is used for model access ONLY** — the agent CLI's LLM calls route through it (`ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL` → gateway), so provider keys + routing + audit/cost live at the gateway. We do **NOT** reuse the existing **chat module** functionality — the worker has its own streaming + message handling. **HARD DEPENDENCY: blocked on the real-provider gateway work (no-fake directive) — workers can't call real models until gateway adapters exist**
- [ ] **Runtime = the coding-agent SDK/CLI (Claude / Codex) run as-is inside the sandbox.** Its OWN runtime, independent of (a) the existing chat module (no reuse of its chat functionality) and (b) the internal `agent_loops`. Start with the agent SDK as-is; unify Codex + Claude later (deferred)
- [ ] **Interactive mode**: two-pane chat screen; user drives the agent message-by-message (each message = a run); per-step permission prompts answered inline
- [ ] **Autonomous mode**: triggered (e.g. vortex bot assigned to a ticket) → works on its own → reports progress as comments in the ticket / PR thread ("started", "done — here's the PR", "found an issue") → escalates a question back to the thread ONLY when genuinely blocking / architecture-breaking → opens a PR. Human reviews the PR and requests changes via PR comments, which the bot picks up
- [ ] **Worker screen = two panes** (interactive mode):
  - [ ] Left — **interactive agent chat**: live stream of the agent (Claude/Codex) terminal output; user sends messages to drive it
  - [ ] Right — **run-scoped panel**: highlighted (syntax-colored) code diff + list of changed files for the selected run; varies by task type
- [ ] **Run = one user-message → agent-work cycle.** Each message the user sends to the worker starts a new run
  - [ ] Run status: `running` | `error` | `finished` | `success`
  - [ ] Each run tracks its own changes — files changed + diffs produced during that run
  - [ ] User can switch between runs and see exactly what changed in each (per-run diff history)
  - [ ] Message during an active run → UI lets the user **choose: interrupt** (stop & redirect the current run) **or queue** (new run after the current finishes)
  - [ ] Per-run changes attributed via git working-tree snapshot (diff between run-start and run-end on the shared tree)
- [ ] **Worker chat = a NEW chat functionality, separate from the existing chat module** (this IS the "worker thread" — one and the same concept):
  - [ ] Why separate: the existing **chat module** is built for **LLM providers** (provider request/response + token streaming). The worker chat is built for the **agent SDK** (Claude/Codex) — a different streaming + event/node model (tool calls, permission prompts, stdio) — so it cannot reuse the LLM-provider chat
  - [ ] Does the same job as our chat (a thread of messages with live streaming), but streams the **agent SDK's output**, brokered by the in-sandbox runner
  - [ ] Owns its own thread store (`worker_messages`); persists across the worker's life (idle included)
  - [ ] (Distinct from the external ticket/PR thread that autonomous mode posts comments to)
- [ ] Deferred: multiple workers per VM · Codex+Claude unification · merging the regular chat and worker-chat into one shared experience

> **⚠️ NOTE — agent-SDK interaction features still to discover.** The Claude/Codex agent SDK has runtime interaction patterns we haven't fully specced. Known example: the agent requests **per-step permission** (read file, edit, delete, run a shell command) and the user **accepts/declines inline in the chat** — finer-grained than the M-of-N approval gates below. Expect more such "hidden" features (tool-permission prompts, confirmations, interrupts, mid-run plan edits) to surface while integrating the SDK; we'll handle them as we go and fold them into this spec when discovered.

## Module Boundary

### Owns

- [ ] `worker_pools` (sandbox templates, allow-list of repos)
- [ ] `workers` (first-class spawned worker = the task: mode, lifecycle state, bound VM/sandbox, model, connector, trigger)
- [ ] ~~`worker_tasks`~~ — merged into `workers` (a worker IS a task)
- [ ] `worker_runs` (one per user-message → agent-work cycle; tracks per-run status + file changes)
- [ ] `worker_messages` (the worker's own agent-SDK **chat thread** — a new chat functionality, separate from the LLM-provider chat module)
- [ ] `worker_events` (append-only stream: every shell cmd, file edit, tool call, agent message)
- [ ] `worker_artifacts` (PR url, diff, logs, screenshots)
- [ ] `worker_approvals` (plan approval, PR approval, budget-overrun approval)
- [ ] `worker_sandboxes` (running sandbox state)
- [ ] `worker_secrets_grants` (which secrets injected into which run)
- [ ] `worker_egress_rules`
- [ ] `git_integrations`, `issue_tracker_integrations`

### Consumes from Control Plane

- [ ] auth / RBAC / audit / usage / webhooks / settings / BlobStore (logs + artifacts)

### Consumes from Gateway

- [ ] All LLM calls for planning, acting, reflecting

### Optionally consumes from RAG

- [ ] Worker can query org KB or repo-specific KB during a task
- [ ] Worker can store learned facts as repo-scoped memories (via Memories module)

### Exposed to other modules (internal contracts)

- [ ] `submit_task(task_input, trigger_source, actor) -> task_id`
- [ ] `cancel_task(task_id, actor)`
- [ ] `stream_events(task_id) -> SSE`
- [ ] Used by chat (assign-to-worker action), assistants (worker as a tool)

## Features — In Scope

### Worker Pools & Templates

- [ ] Pool: a named worker template + scope (allowed repos, allowed branches, budget cap, sandbox provider)
- [ ] Template: base image (language toolchain), preinstalled tools, allowed MCP tools, default model
- [ ] Bundled templates: `python`, `node`, `go`, `rust`, `polyglot`
- [ ] Org admin can define custom templates (Dockerfile + tool list)

### Sandbox Providers

- [ ] Sandbox abstraction: `provision()`, `exec(cmd)`, `read_file(path)`, `write_file(path, bytes)`, `kill()`, `snapshot()`, `restore(snapshot)`
- [ ] Bundled providers:
  - [ ] `docker` (local dev; default)
  - [ ] `kubernetes` (prod; gVisor / Kata runtime for isolation)
  - [ ] `firecracker` (microVM, future-ready slot, optional)
  - [ ] `e2b` / `daytona` (third-party managed) — adapters only, opt-in
- [ ] Sandbox lifecycle: provision → checkout → run → snapshot → destroy
- [ ] Resource limits: CPU, RAM, disk, wall-time, max processes
- [ ] No persistent state by default; opt-in snapshot for long tasks
- [ ] **v1 worker exception**: the sandbox/VM persists bound to its worker (stays allocated while the worker is `idle`), destroyed only when the worker is stopped — not per task
- [ ] **Idle cost control (proposed)**: auto-hibernate the VM after N minutes of inactivity (snapshot + suspend), restore on next message — avoids paying for hot idle VMs

### Git Integration

- [ ] Provider abstraction: `clone`, `branch`, `commit`, `push`, `create_pr`, `comment_pr`, `read_pr`, `update_pr`
- [ ] Bundled: `github`, `gitlab`, `bitbucket`, `gitea`, `azure_devops`
- [ ] **v1 priority connector: GitLab** — worker spawn starts with a GitLab repo (other providers follow)
- [ ] Bot identity ("vortex bot") must be granted repo access before spawn: GitLab project/group access token or OAuth app (GitHub App for GitHub)
- [ ] Auth: org-level GitHub App (preferred), org token, or per-user OAuth
- [ ] Per-repo allow list (which repos a pool may touch)
- [ ] PR template configurable per pool (description, test plan, generated-by tag)
- [ ] Branch naming convention (`worker/<task-id>-<slug>`)
- [ ] Worker never pushes to default branch directly
- [ ] **Interactive-mode git timing (proposed)**: branch created at spawn; commit/push/open-PR are user-driven (ask the agent in chat, or UI buttons) — not automatic per run
- [ ] **Autonomous-mode git timing**: agent branches, commits, and opens the PR on its own; review loop via PR comments

### Issue Tracker Integration

- [ ] Provider abstraction: `list_issues`, `read_issue`, `comment_issue`, `set_status`, `webhook_events`
- [ ] Bundled: `jira_cloud`, `linear`, `github_issues`, `gitlab_issues`, `azure_boards`
- [ ] Webhook receiver: new issue with magic label/keyword (or bot assigned to ticket) → spawn an **autonomous** worker
- [ ] Autonomous worker reports back in the ticket / PR thread: started → progress → "done, here's the PR" → escalates a blocking question only when genuinely necessary
- [ ] Per-tracker mapping: which project → which worker pool

### Task Triggers

- [ ] From chat: user assigns task ("ship a fix for X to repo Y")
- [ ] From Jira/Linear: webhook on label / status change
- [ ] From Github issue: comment `/worker do this` (configurable trigger phrase)
- [ ] From PR comment: `/worker address feedback`
- [ ] From REST API: `POST /v1/workers/tasks`
- [ ] From schedule: cron-driven recurring tasks (e.g., nightly dependency update)

### Task Lifecycle

- [ ] States: `queued → planning → awaiting_plan_approval (optional) → executing → awaiting_pr_approval (optional) → completed | failed | cancelled`
- [ ] Plan approval gate (configurable per pool / task): worker proposes plan → human approves → executes
- [ ] PR approval gate: worker creates PR in draft → human flips to ready
- [ ] Budget overrun gate: pause at budget threshold, request approval, resume
- [ ] Pause / resume / cancel from UI
- [ ] Timeout policy (max wall-clock per task; defaults from pool)

### Agent Loop

- [ ] Phases: `plan` → `act` (loop: observe → think → tool-call → observe) → `verify` → `reflect`
- [ ] Planning step produces a written plan + step list (visible to user)
- [ ] Acting step uses tool registry
- [ ] Verification step runs tests / linters / type-check
- [ ] Reflection step decides: done, retry, escalate
- [ ] Configurable agent loop variant (e.g., ReAct, Plan-and-Execute, OpenHands-style); abstraction `agent_loops/protocol.py`

### In-Sandbox Agent Runner (harness)

A small runner script/process injected into the VM on provision — the sandbox-side half of `agent_runtime/`. The orchestrator can't drive the agent CLI across the VM boundary, so this runner brokers everything.

- [ ] Bootstraps on VM provision: installs/launches the chosen agent CLI (Claude Agent SDK / Codex) with the selected model + cloned repo + repo conventions (`CLAUDE.md` / `AGENTS.md`)
- [ ] Owns the agent process lifecycle inside the VM: start, restart, stop, health
- [ ] Bidirectional control channel to the orchestrator: pipes user messages IN, streams terminal stdio + structured events OUT
- [ ] Surfaces agent-SDK interaction prompts (per-step tool permission, confirmations, interrupts) and relays the user's accept/decline back to the agent
- [ ] Reports per-run signals: run start/finish, status, changed files + diffs
- [ ] Normalizes Claude vs Codex behind one wire protocol so the orchestrator is runtime-agnostic
- [ ] Injected secrets available as env; never logged (see Secrets)
- [ ] Transport between runner ↔ orchestrator: TBD (stdio over the sandbox exec channel, or a small local server in the VM) — design decision deferred

### Agent Skills (injected into the agent SDK)

We customize agent behavior by injecting **skills** into the agent SDK's context — NOT by writing a custom agent loop (the SDK already has its own loop).

- [ ] A **skill** = a reusable capability package (instructions + optional helper scripts/tools) injected into the running agent's context for a task
- [ ] Skills selected per worker / pool / task (e.g. `fix-bug`, `write-tests`, `refactor`, `dependency-update`, repo conventions)
- [ ] In-sandbox runner installs/sets up the selected skills in the agent's environment before/at launch
- [ ] Repo conventions (`CLAUDE.md` / `AGENTS.md`) loaded as part of the injected context
- [ ] Skill registry: bundled starter skills + org-defined custom skills (configurable abstraction)
- [ ] Exact per-SDK injection mechanism (Claude Agent SDK vs Codex) — **verify at implementation** (model/SDK APIs change)

### Tools (worker-callable)

- [ ] `shell` (run command in sandbox; output captured + streamed)
- [ ] `read_file` / `write_file` / `edit_file` (with diff)
- [ ] `code_search` (ripgrep + ast-grep)
- [ ] `run_tests` (project-configured)
- [ ] `run_build`
- [ ] `lint` / `format`
- [ ] `git_status` / `git_diff` / `git_commit` / `git_push`
- [ ] `open_pr` / `comment_pr`
- [ ] `web_fetch` (governed by egress policy)
- [ ] `web_search` (via RAG search providers)
- [ ] `kb_search` (org KBs via RAG)
- [ ] `memory_recall` / `memory_remember`
- [ ] `browser` (Playwright in sandbox — optional, for UI verification)
- [ ] MCP server bridge: any MCP server allow-listed for the pool is exposed as tools
- [ ] Tool registry abstraction with per-pool allow list

### Live Streaming UI

- [ ] SSE stream of `worker_events` to the browser
- [ ] Event kinds: `agent_thought`, `tool_call`, `tool_result`, `file_changed`, `shell_output`, `agent_stdio` (raw SDK terminal), `pr_created`, `error`, `phase_changed`, `approval_requested`, `permission_request` (inline tool prompt), `run_started`, `run_finished`
- [ ] Side panels: terminal output, file tree + diff viewer, tool log, agent reasoning
- [ ] Inline interventions: pause, send message to worker, edit plan, cancel
- [ ] Browser-tool view streams page screenshots/snapshots when used

### Approvals & Human-in-the-Loop

- [ ] Approval request UI in chat / inbox / email / Slack
- [ ] **Inline per-step tool-permission prompts** from the agent SDK (read / edit / delete / run-command) — user accepts/declines directly in the worker chat; finer-grained and real-time vs the M-of-N gates below (exact set of prompt types TBD — see agent-SDK discovery note)
- [ ] Approval policies per pool: `always`, `never`, `on_cost_above`, `on_files_matching`, `on_first_run_for_repo`
- [ ] Approval decisions audited
- [ ] Multiple approvers (configurable; M-of-N)

### Cost & Budget

- [ ] Per-task cost (LLM tokens + sandbox minutes + storage)
- [ ] Per-pool budget; pause + approve to continue when exceeded
- [ ] Cost shown live during task
- [ ] Webhook + notification on budget threshold

### Secrets

- [ ] Per-pool / per-repo secret bindings (e.g., NPM token, AWS read key for staging)
- [ ] Secrets injected as env vars in sandbox; never written to logs
- [ ] Secret detection on diffs before commit (block leak)
- [ ] Audit trail of secret grants

### Network Policy

- [ ] Per-pool egress allow-list (domains / IP ranges)
- [ ] Default-deny; explicit allow required for outbound
- [ ] Common allow presets (npm/pypi/crates/etc.)
- [ ] DNS resolution restricted to allow-list
- [ ] Audit on blocked egress attempts

### Observability

- [ ] Trace per task (gateway request traces correlated by task_id)
- [ ] Metrics: tasks completed, fail rate, mean tokens per task, mean wall-clock, mean cost
- [ ] Per-repo / per-template breakdowns
- [ ] Replay: re-run a historic task with same inputs in fresh sandbox

### Code Quality Hooks

- [ ] Run repo-defined commands (test, lint, typecheck, build) at verify step
- [ ] If repo has `AGENTS.md` / `CLAUDE.md` / `.cursorrules` → load as agent instructions
- [ ] Detect project's package manager + test command on first run; cache in repo memory
- [ ] Enforce conventional commits (configurable)

### Multi-Worker Coordination (minimal v1)

- [ ] Tasks are independent by default
- [ ] One worker per repo branch at a time (lock by branch name)
- [ ] No cross-task message passing in v1

### Audit Coverage

- [ ] Every shell command audited with stdout/stderr hash
- [ ] Every file write audited with before/after hash
- [ ] Every PR created audited with diff hash + url
- [ ] Every approval audited

## Features — Out of Scope (for now)

- [ ] Browser-only / desktop-control tasks (RPA-style workflows beyond coding)
- [ ] Multi-worker swarms (agent-to-agent collaboration)
- [ ] Live-coding pair-programming UI (single autonomous worker view only)
- [ ] Auto-merge to default branch
- [ ] Production-deploy actions (workers may push to staging at most)
- [ ] Workers running on the user's local machine (cloud sandboxes only v1)
- [ ] IDE plugin integrations (workers visible only in the suite UI for v1)
- [ ] Custom sandbox provider upload UI (config-only)
- [ ] Marketplace of agent templates from third parties
- [ ] Voice-triggered tasks
- [ ] Agent learning across orgs
- [ ] Multiple workers per VM (v1 is worker-per-VM, 1:1) — deferred
- [ ] Unified Codex + Claude agent experience (start each independently) — deferred
- [ ] Merging the regular chat module and worker-chat into one shared runtime/UX — deferred

## Configurable Abstractions

### Sandbox Provider (`workers/sandboxes/`)

- [ ] Interface above
- [ ] Bundled: `docker`, `kubernetes`, `e2b`, `daytona`, `firecracker` (slot)

### Git Provider (`workers/git/`)

- [ ] Interface: `clone`, `branch`, `commit`, `push`, `create_pr`, `comment_pr`, `read_pr`, `update_pr`, `parse_pr_event(webhook)`
- [ ] Bundled: `github`, `gitlab`, `bitbucket`, `gitea`, `azure_devops`

### Issue Tracker (`workers/issues/`)

- [ ] Interface: `read_issue`, `comment_issue`, `set_status`, `subscribe_webhook`, `parse_webhook_event`
- [ ] Bundled: `jira_cloud`, `linear`, `github_issues`, `gitlab_issues`, `azure_boards`

### Tool (`workers/tools/`)

- [ ] Interface: `name`, `schema`, `invoke(args, sandbox, ctx) -> result`
- [ ] Bundled tools listed above
- [ ] MCP bridge as a generic adapter

### Skill (`workers/skills/`)

- [ ] A skill package = `{name, instructions, optional tools/scripts, applies_to}` injected into the agent SDK context by the in-sandbox runner
- [ ] Bundled starter set (`fix-bug`, `write-tests`, `refactor`, `dependency-update`); org can add custom skills
- [ ] Customization happens via skills, not custom agent loops

### Agent Runtime (`workers/agent_runtime/`) — v1 primary

- [ ] Drives a real coding-agent CLI/SDK inside the sandbox: streams terminal stdio out + accepts interactive user input
- [ ] Bundled: `claude` (Claude Agent SDK / CLI), `codex`
- [ ] Priority over internal `agent_loops` (those become a secondary/headless path); Codex + Claude unified into one experience later (deferred)
- [ ] Real SDK required — no fake agent runtime in the shipping path (per global no-fake directive)
- [ ] Surfaces SDK interaction events to the chat: tool-permission prompts, confirmations, interrupts (see discovery note — exact set TBD)
- [ ] Server-side adapter pairs with the **In-Sandbox Agent Runner** (see Features) — runner drives the CLI in the VM; adapter speaks its wire protocol

### Agent Loop (`workers/agent_loops/`) — NOT the customization path

> Customization happens via **injected skills** (see Agent Skills), not a custom loop — the agent SDK has its own loop. So these internal loops are NOT how we tailor worker behavior.
> Keep ONLY as a fallback to run models the Claude Code / Codex CLI can't drive (Gemini / Mistral / local via the gateway). If v1 is SDK-only, this + the legacy "Agent Loop" / "Task Lifecycle" (plan→act→verify→reflect) framing is dead code.
> Kept in tree for now, not wired as a runtime.

- [ ] Interface: `run(task, tools, gateway) -> AsyncIterator[Event]`
- [ ] Bundled: `react`, `plan_and_execute`, `openhands_style`

### Trigger Source (`workers/triggers/`)

- [ ] Interface: `parse(webhook_payload) -> TaskInput | None`
- [ ] Bundled: `chat`, `rest_api`, `jira_webhook`, `linear_webhook`, `github_issue_comment`, `github_pr_comment`, `schedule_cron`

## Data Model (sketch)

- [ ] `worker_pools(id, org_id, name, template, sandbox_provider, repo_allow_list_json, budget_cents_per_task, default_model, settings_json, enabled)`
- [ ] `workers(id, org_id, pool_id NULLABLE, name, state, mode, model, connector_json, repo_url, sandbox_id, trigger_source NULLABLE, trigger_payload_json NULLABLE, created_by, created_at, last_active_at)` — `mode`: interactive|autonomous; `state`: idle|provisioning|running|error|stopped; bound 1:1 to a sandbox/VM for v1. **A worker IS a task** — legacy `worker_tasks` merges into this row
- [ ] ~~`worker_tasks(...)`~~ — **merged into `workers`** (task ≡ worker); trigger source/payload + status now live on the worker row
- [ ] `worker_runs(id, worker_id, seq_no, user_message, status, started_at, ended_at, sandbox_id, cost_cents, error)` — one per user-message → agent cycle; `status`: running|error|finished|success
- [ ] `worker_run_changes(id, run_id, file_path, change_kind, additions, deletions, diff_ref)` — files changed during a run; drives the right-pane highlighted diff + changed-files list
- [ ] `worker_messages(id, worker_id, run_id NULLABLE, role, content, ts)` — the worker's own **chat thread** (a new agent-SDK chat functionality, separate from the LLM-provider chat module); `role`: user|agent|system
- [ ] `worker_events(id, run_id, kind, payload_json, ts)` — append-only, partitioned daily
- [ ] `worker_artifacts(id, run_id, kind, ref, meta_json)` — PR url, log file, screenshot, diff
- [ ] `worker_approvals(id, task_id, kind, requested_at, decided_at, decided_by, decision, reason)`
- [ ] `worker_sandboxes(id, worker_id, run_id NULLABLE, provider, provider_resource_id, state, allocated_at, released_at)` — bound to the worker (persists across runs for v1); `run_id` set while a task is active
- [ ] `worker_secrets_grants(id, pool_id, secret_ref, allow_repos_json)`
- [ ] `worker_egress_rules(id, pool_id, allow_list_json)`
- [ ] `git_integrations(id, org_id, kind, config_encrypted, enabled)`
- [ ] `issue_tracker_integrations(id, org_id, kind, config_encrypted, project_mapping_json, enabled)`

## Public API (sketch)

- [ ] `GET/POST /v1/workers/pools`
- [ ] `GET/POST /v1/workers/instances` (list / spawn a worker — spawn provisions VM + clones repo + launches the agent)
- [ ] `GET /v1/workers/instances/{id}` / `POST /v1/workers/instances/{id}/stop`
- [ ] `GET /v1/workers/instances/{id}/stream` (SSE — live agent terminal stdio)
- [ ] `POST /v1/workers/instances/{id}/message` (user input → running agent; interactive steering — starts a new run)
- [ ] `GET /v1/workers/instances/{id}/runs` (list runs + per-run status)
- [ ] `GET /v1/workers/runs/{run_id}/changes` (changed files + highlighted diffs for one run)
- [ ] `POST /v1/workers/instances/{id}/permissions/{prompt_id}` (allow/deny an inline agent-SDK tool-permission prompt — shape TBD)
- [ ] `POST /v1/workers/tasks` (submit)
- [ ] `GET /v1/workers/tasks/{id}` (state)
- [ ] `GET /v1/workers/tasks/{id}/events` (SSE stream)
- [ ] `GET /v1/workers/tasks/{id}/artifacts`
- [ ] `POST /v1/workers/tasks/{id}/cancel`
- [ ] `POST /v1/workers/tasks/{id}/pause` / `resume`
- [ ] `POST /v1/workers/tasks/{id}/message` (user message to running worker)
- [ ] `POST /v1/workers/approvals/{id}/decide`
- [ ] `GET/POST /v1/workers/git-integrations`
- [ ] `GET/POST /v1/workers/issue-tracker-integrations`
- [ ] `POST /v1/workers/webhooks/github` (etc per provider)
- [ ] `GET /v1/workers/health`

## UI Surface

- [ ] Workers → Workers list (spawned workers + lifecycle state idle/running/error; "spawn worker" → choose model + **mode (interactive/autonomous)** + GitLab connector)
- [ ] Worker detail → two-pane: LEFT interactive agent chat (streamed Claude/Codex terminal, user can steer; each user message = a run with status running/error/finished/success); RIGHT run-scoped panel — highlighted code diff + changed-files list for the selected run; switch runs to see each run's changes
- [ ] Workers → Tasks (active + history; filter by pool / repo / status)
- [ ] Task detail → live view (events stream, terminal, diff, reasoning side-by-side)
- [ ] Task detail → approvals
- [ ] Task detail → artifacts (PR link, downloadable logs, snapshots)
- [ ] Pools (list + CRUD + template editor)
- [ ] Integrations (Github, Gitlab, Jira, Linear, …)
- [ ] Settings (budgets, egress, secrets, approval policies)
- [ ] Analytics (success rate, cost, time per task)

## Dependencies on Other Modules

- [ ] Control Plane (hard)
- [ ] Gateway (hard — **SHIPPING BLOCKER**: worker LLM calls route through the gateway, which needs real providers, not FakeProvider)
- [ ] RAG (soft — only if worker uses KB / web search tools)
- [ ] Memories (soft — only if repo-scoped memory enabled)

## Acceptance Criteria

- [ ] User spawns a worker (model + GitLab repo) → VM provisions, repo clones, agent launches; running a task streams the agent terminal live in the left pane while file diffs appear in the right pane; user can type to steer the agent mid-run
- [ ] A Github issue labeled `worker` triggers a task; worker clones the repo, plans, executes, runs tests, opens a draft PR linked back to the issue
- [ ] User can watch the terminal + diff + reasoning live in the browser; latency < 1s per event
- [ ] User cancels mid-run → sandbox killed, task marked cancelled, audit captured
- [ ] Worker exceeds pool budget → execution pauses, approval request appears, resume continues
- [ ] Worker attempts to push to default branch → blocked by policy, audited
- [ ] Worker attempts egress to a non-allow-listed domain → blocked, audited
- [ ] Secret never appears in any log or PR diff (verified by secret-scanner in test)
- [ ] GDPR delete on the org cascades to all worker tasks / events / artifacts

## Testing

- [ ] Unit tests per file in `server/api/src/ai_portal/workers/` (new module) and its sub-packages
- [ ] Sandbox tests use a `fake` provider that simulates exec/read/write without containers — test-only double, never a shipping runtime path (real sandboxes ship)
- [ ] Git provider tests use `responses` / `respx` to mock API
- [ ] Run only touched-file tests during implementation
- [ ] Defer E2E to the final verification step
- [ ] E2E targets (added at the end): submit task from chat → see live stream → PR url appears; Github webhook → auto task → PR; approval gate flow; budget pause/resume; cancel mid-run cleanup
