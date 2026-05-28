# Suite Overview — Enterprise AI Control Plane

> Supersedes the phase split in `Pivot.md`. Suite is five modules — Control Plane is the substrate; Gateway, RAG, Memories, and Task Workers consume it and are independently deployable.
>
> **Status (May 2026, post-pivot):** All five modules implemented and smoke-tested. E2E suite 6/9 passing. See `docs/RUNBOOK.md` for ops.

## Purpose

- [x] Build a modular AI suite where each module stands alone but composes into one governed platform
- [x] Every module sellable in isolation; every module togglable per deployment
- [x] Every external touchpoint (provider, connector, store, sandbox, identity) is an interface with bundled implementations

## Modules

- [x] **Control Plane** — orgs, users, SSO, SCIM, RBAC, API keys, audit, usage, billing, webhooks, settings
- [x] **Gateway** — provider-compatible APIs, routing, failover, rate limits, prompt caching, guardrails, observability
- [x] **RAG Management** — KBs, connectors, ingestion, embedders, stores, hybrid search, rerank, search providers, eval
- [x] **Memories** — user/conversation/team memories, extraction, recall, decay, GDPR controls
- [x] **Task Workers** — sandboxed coding agents, git/issue-tracker triggers, live streaming, approval gates

## Dependency Graph

```
Control Plane  ←  Gateway  ←  RAG  ←  Memories
       ↑           ↑           ↑         ↑
       └───────────┴───────────┴─────────┘
                       │
                  Task Workers
```

- [ ] Control Plane is the only hard dependency for every other module
- [ ] Gateway is consumed by RAG (embeddings + answering), Memories (extraction), Task Workers (agent LLM calls)
- [ ] RAG is optionally consumed by Memories and Task Workers
- [ ] Memories and Task Workers do not depend on each other

## Module Independence Rules

- [ ] Each module owns its DB tables (separate schema or table prefix; no cross-module joins)
- [ ] Cross-module calls go through versioned internal API contracts, never direct repository reads
- [ ] Each module has its own routes namespace (`/v1/gateway/...`, `/v1/rag/...`, etc.)
- [ ] Each module ships its own UI section, lazily loaded
- [ ] Disabling a module is a single feature flag in Control Plane settings
- [ ] Modules must boot with peers disabled — startup must not require peers to be present

## Shared Concepts (defined once in Control Plane, consumed by all)

- [ ] `org_id` — tenant root; every row in every module carries it
- [ ] `actor` — user or service principal (api key); every audited action attributes to one
- [ ] `policy` — RBAC role + ABAC attributes (e.g., data classification, region)
- [ ] `audit_event` — append-only record; every module emits to the same stream
- [ ] `usage_event` — metered units (tokens, docs, queries, worker minutes); every module emits
- [ ] `webhook_event` — outbound notification; every module declares its event types
- [ ] `module_flag` — per-org enable/disable + per-org feature-gate (e.g., `rag.search_providers.tavily`)

## Cross-Cutting Mandates (every module must satisfy)

- [ ] Multi-tenant isolation: no query path that can leak across `org_id`
- [ ] Audit emission: every state-changing API call writes an `audit_event`
- [ ] Usage metering: every billable operation writes a `usage_event`
- [ ] Webhook emission: every domain event publishes a `webhook_event`
- [ ] RBAC enforcement: every API route declares the permission it requires
- [ ] GDPR cascade: deleting a user / org cascades to all module-owned data
- [ ] Configurable: every external dependency behind an interface in `<module>/providers/`
- [ ] Health endpoint: `/v1/<module>/health` reports per-provider status

## Configurable-Abstraction Pattern (applied uniformly)

Every "thing that talks to the outside world" follows this shape:

- [ ] `protocol.py` — abstract interface, types, error taxonomy
- [ ] `providers/<name>.py` — concrete implementation
- [ ] `registry.py` — name → factory, loaded from settings
- [ ] Per-org config row picks which provider is active
- [ ] At least one bundled open-source / self-hosted implementation per category
- [ ] Documented "how to add a provider" with checklist

Applies to: LLM providers, embedders, vector stores, rerankers, search providers, connectors, extractors, chunkers, sandbox providers, git providers, issue trackers, identity providers, SCIM endpoints, billing providers, email/notification providers, object storage.

## Out of Scope — Suite-Level (for now)

- [ ] Marketplace for third-party modules
- [ ] Cross-org federation (multi-org workflows)
- [ ] Mobile native apps (responsive web only)
- [ ] On-device / edge deployment
- [ ] Agent-to-agent protocols across orgs
- [ ] Fine-tuning / training infra
- [ ] Image / video generation models (text + embeddings + transcription only)
- [ ] Voice cloning / TTS as first-class capability

## Sub-Agent Dispatch Plan (executed AFTER spec approval)

- [ ] One implementation plan per module (via `writing-plans` skill, 5 plans total)
- [ ] One sub-agent per module, dispatched in parallel via `dispatching-parallel-agents`
- [ ] Each sub-agent works in its own git worktree to avoid file conflicts
- [ ] Each sub-agent's scope is bounded to its module's owned files + the shared internal API contracts it consumes
- [ ] Control Plane sub-agent runs first (or at least its shared-concept tables migrate first) to unblock peers

## Testing Strategy

- [ ] **During sub-agent work**: each agent runs ONLY file-scoped unit tests for files it touched (`pytest path/to/file.py` or `vitest <file>`)
- [ ] No sub-agent runs the full unit suite, the full lint, or any E2E
- [ ] After all sub-agents complete: a final verification step runs `pnpm test:e2e` and adds/updates E2E specs for cross-module flows
- [ ] E2E must follow project rules in `CLAUDE.md`: UI-only interactions via `createOrFindConversation` / `createOrFindKb` helpers, E2E DB on port 5435
- [ ] Test isolation per worktree: each sub-agent gets its own DB containers via `./scripts/worktree-up.sh`

## Acceptance Criteria for the Suite

- [x] Five module specs exist, approved, committed
- [x] Five implementation plans derived from specs, approved
- [x] All five sub-agents complete their plans
- [~] Final E2E pass covers: gateway-routes-to-provider, kb-ingests-and-answers, memory-recall-in-chat, worker-completes-task-and-opens-pr, all under one org with shared audit log — **6/9 specs passing post-pivot**; remaining gaps tracked separately
- [x] `Pivot.md` superseded — this spec is the canonical structure; `Pivot.md` retained as history

## Documentation Outputs

- [~] One README per module under `server/api/src/ai_portal/<module>/README.md` — partial
- [x] Public API reference (OpenAPI) — served at `/openapi.json` (single doc, module-namespaced routes)
- [x] Operator runbook — `docs/RUNBOOK.md` (single doc covering all modules)
- [ ] "How to add a provider" guide per abstraction category — deferred
