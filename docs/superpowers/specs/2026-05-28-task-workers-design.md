# Task Workers — Design Spec

## Purpose

- [ ] Autonomous AI coding agents that take a task, work in an isolated VM/container connected to git, and open a reviewable PR
- [ ] Triggered from chat, from Jira/Linear/Github issues, from PR comments, or scheduled
- [ ] Live-streamed to the browser so humans can watch and intervene
- [ ] Governed by the same Control Plane (audit, RBAC, budget, guardrails) as the rest of the suite
- [ ] Buyer: CTO / Head of Engineering / Eng Productivity Lead
- [ ] Comparable to: Devin, Cursor Background Agents, Cognition, Sweep, OpenHands

## Module Boundary

### Owns

- [ ] `worker_pools` (sandbox templates, allow-list of repos)
- [ ] `worker_tasks` (one per assigned task)
- [ ] `worker_runs` (one per execution attempt; tasks can have retries)
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

### Git Integration

- [ ] Provider abstraction: `clone`, `branch`, `commit`, `push`, `create_pr`, `comment_pr`, `read_pr`, `update_pr`
- [ ] Bundled: `github`, `gitlab`, `bitbucket`, `gitea`, `azure_devops`
- [ ] Auth: org-level GitHub App (preferred), org token, or per-user OAuth
- [ ] Per-repo allow list (which repos a pool may touch)
- [ ] PR template configurable per pool (description, test plan, generated-by tag)
- [ ] Branch naming convention (`worker/<task-id>-<slug>`)
- [ ] Worker never pushes to default branch directly

### Issue Tracker Integration

- [ ] Provider abstraction: `list_issues`, `read_issue`, `comment_issue`, `set_status`, `webhook_events`
- [ ] Bundled: `jira_cloud`, `linear`, `github_issues`, `gitlab_issues`, `azure_boards`
- [ ] Webhook receiver: new issue with magic label/keyword → auto-submit task
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
- [ ] Event kinds: `agent_thought`, `tool_call`, `tool_result`, `file_changed`, `shell_output`, `pr_created`, `error`, `phase_changed`, `approval_requested`
- [ ] Side panels: terminal output, file tree + diff viewer, tool log, agent reasoning
- [ ] Inline interventions: pause, send message to worker, edit plan, cancel
- [ ] Browser-tool view streams page screenshots/snapshots when used

### Approvals & Human-in-the-Loop

- [ ] Approval request UI in chat / inbox / email / Slack
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

### Agent Loop (`workers/agent_loops/`)

- [ ] Interface: `run(task, tools, gateway) -> AsyncIterator[Event]`
- [ ] Bundled: `react`, `plan_and_execute`, `openhands_style`

### Trigger Source (`workers/triggers/`)

- [ ] Interface: `parse(webhook_payload) -> TaskInput | None`
- [ ] Bundled: `chat`, `rest_api`, `jira_webhook`, `linear_webhook`, `github_issue_comment`, `github_pr_comment`, `schedule_cron`

## Data Model (sketch)

- [ ] `worker_pools(id, org_id, name, template, sandbox_provider, repo_allow_list_json, budget_cents_per_task, default_model, settings_json, enabled)`
- [ ] `worker_tasks(id, org_id, pool_id, trigger_source, trigger_payload_json, title, description, status, created_by, created_at, completed_at)`
- [ ] `worker_runs(id, task_id, attempt_no, status, started_at, ended_at, sandbox_id, cost_cents, error)`
- [ ] `worker_events(id, run_id, kind, payload_json, ts)` — append-only, partitioned daily
- [ ] `worker_artifacts(id, run_id, kind, ref, meta_json)` — PR url, log file, screenshot, diff
- [ ] `worker_approvals(id, task_id, kind, requested_at, decided_at, decided_by, decision, reason)`
- [ ] `worker_sandboxes(id, run_id, provider, provider_resource_id, state, allocated_at, released_at)`
- [ ] `worker_secrets_grants(id, pool_id, secret_ref, allow_repos_json)`
- [ ] `worker_egress_rules(id, pool_id, allow_list_json)`
- [ ] `git_integrations(id, org_id, kind, config_encrypted, enabled)`
- [ ] `issue_tracker_integrations(id, org_id, kind, config_encrypted, project_mapping_json, enabled)`

## Public API (sketch)

- [ ] `GET/POST /v1/workers/pools`
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
- [ ] Gateway (hard)
- [ ] RAG (soft — only if worker uses KB / web search tools)
- [ ] Memories (soft — only if repo-scoped memory enabled)

## Acceptance Criteria

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
- [ ] Sandbox tests use a `fake` provider that simulates exec/read/write without containers
- [ ] Git provider tests use `responses` / `respx` to mock API
- [ ] Run only touched-file tests during implementation
- [ ] Defer E2E to the final verification step
- [ ] E2E targets (added at the end): submit task from chat → see live stream → PR url appears; Github webhook → auto task → PR; approval gate flow; budget pause/resume; cancel mid-run cleanup
