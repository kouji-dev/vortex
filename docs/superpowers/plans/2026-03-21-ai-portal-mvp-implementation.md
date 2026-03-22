# AI Portal (Self-Hosted OSS) MVP Implementation Plan

> **For agentic workers:** REQUIRED: Use @superpowers:subagent-driven-development (if subagents available) or @superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a minimal self-hosted AI portal: authenticated users browse a catalog of assistants, chat via a unified model gateway, and use document-grounded RAG on allowed corpora—with usage logging suitable for later FinOps and audit.

**MVP-0 first:** Use the focused bootstrap plan [`2026-03-21-mvp-0-bootstrap.md`](./2026-03-21-mvp-0-bootstrap.md) (API + web + Compose + CI + health). This file stays the **full syllabus** and **chunk map** for later slices.

**Architecture:** Single-tenant-first deployment (one organization) with **FastAPI** as the system of record for users, assistants, permissions, and **chat conversations** (threads); **PostgreSQL + pgvector** for relational data and embeddings; **Redis + Celery** for ingestion and heavy jobs; **LiteLLM** (or direct provider SDK initially) as the model access layer; **React + TypeScript + TanStack Query/Router** for the web UI. Identity: [Entra auth spec](../specs/2026-03-22-auth-entra-design.md). Everything runnable via **Docker Compose** on a developer machine and portable to Kubernetes later.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, Celery, Redis, PostgreSQL 16+ with pgvector, uvicorn, React 18+, TypeScript, Vite, TanStack Query, TanStack Router, LiteLLM (optional container), Langfuse (optional container), Docker, Docker Compose.

**Prerequisites / note:** This plan assumes requirements aligned with the earlier feature map (catalog, RBAC, RAG, APIs, observability). If scope changes, revise Chunk 1–2 first. Formal brainstorming workflow would add `docs/superpowers/specs/2026-03-21-ai-portal-design.md` and user approval before execution—create that doc if you need stakeholder sign-off.

---

## Syllabus: major feature areas (full platform)

This syllabus lists **everything a production-grade self-hosted AI portal typically includes**, independent of MVP scope. Use it as a curriculum checklist for docs, backlog, and compliance conversations. Items marked **(MVP)** appear in the implementation chunks below; others are **phase 2+** unless noted.

### Module 1 — Product experience and change management

| Topic | Outcomes / capabilities |
|--------|---------------------------|
| Assistant catalog (“marketplace”) | Discover, search/filter, detail pages, launch chat or workflow, ownership and lifecycle states (draft / published / deprecated). **(MVP: list + detail + launch)** |
| Profile-aware UX | Home and catalog vary by role; featured assistants; optional favorites/recents. |
| Onboarding | First-login tour, policy acknowledgement, links to acceptable use. |
| Training & enablement | Curated modules, webinars embeds or links, progress optional. |
| FAQ & help center | Editable FAQ, search, escalation paths to support (not the same as RAG corpora). |
| Feedback & support | In-app issue reporting, ticket deep links, release notes. |

### Module 2 — Identity, access control, and governance

| Topic | Outcomes / capabilities |
|--------|---------------------------|
| Authentication | Local accounts, API keys, **OIDC/SAML SSO**, optional SCIM provisioning. MVP: **dev bearer** in repo today; production path — [auth Entra spec](../specs/2026-03-22-auth-entra-design.md), [implementation plan](./2026-03-22-auth-entra.md). |
| Authorization (RBAC/ABAC) | Roles, groups, per-assistant entitlements; admin vs builder vs consumer. **(MVP: roles + ACL)** |
| Data-level access for RAG | Document/collection ACLs enforced at retrieval time; tenant isolation for multi-tenant. **(MVP: per-assistant document scope)** |
| AI usage policy | Link governance rules to features (e.g. block external paste, model allowlists). |
| Approvals | Workflow to publish assistants or connect sensitive knowledge bases. |

### Module 3 — Assistant lifecycle and APIs for business systems

| Topic | Outcomes / capabilities |
|--------|---------------------------|
| Assistant CRUD & versioning | Prompts, parameters, connected tools, knowledge bindings, version history and rollback. **(MVP: CRUD without full versioning)** |
| External API exposure | Stable REST/OpenAPI and/or **OpenAI-compatible** endpoints for CRM, IDE, portals; scoped API keys. **(MVP: internal chat API)** |
| Rate limits & quotas | Per key, per user, per team; HTTP 429 semantics and admin overrides. |
| Webhooks / events (optional) | Assistant published, ingestion completed, policy violation flagged. |

### Module 4 — Model routing, cost, and FinOps

| Topic | Outcomes / capabilities |
|--------|---------------------------|
| Multi-provider routing | Unified gateway to many LLM providers and local inference (e.g. OpenAI-compatible stack). **(MVP: single base URL + key)** |
| Model allowlists | Per environment and per role; block high-cost or non-approved models in prod. |
| Usage metering | Tokens, requests, estimated cost; per user/team/project dashboards. **(MVP: persist conversations/messages; extend to spend)** |
| Budgets & alerts | Soft/hard caps, notifications, admin actions. |
| Fallback & resilience | Retries, circuit breaking, degraded mode messaging. |

### Module 5 — RAG, knowledge bases, and document intelligence

| Topic | Outcomes / capabilities |
|--------|---------------------------|
| Ingestion pipelines | File types, batch vs incremental sync, scheduling, re-embedding on model change. **(MVP: upload + async job)** |
| OCR & complex documents | Scanned PDFs, tables, slides; quality thresholds and quarantine for failures. |
| Chunking & metadata | Strategies per doc type; section titles, page numbers, source URI. **(MVP: simple chunking)** |
| Vector retrieval | pgvector or equivalent; hybrid search (keyword + vector) optional. **(MVP: vector only)** |
| External knowledge sources | Connectors (SharePoint, S3, URLs) and “bring your own” KB APIs. |
| Quality & evaluation | Golden sets, regression tests, **RAGAS** (or similar) in CI; human eval hooks. |
| Grounding & citations | Answer with source references; “insufficient context” behavior. |

### Module 6 — Agents, tools, and safety

| Topic | Outcomes / capabilities |
|--------|---------------------------|
| Orchestration | Multi-step flows, stateful graphs (e.g. LangGraph-style patterns), human-in-the-loop for risky steps. |
| Tool / MCP integration | Register HTTP tools, DB tools behind policies, **MCP servers** for IDE/agents. |
| Guardrails | PII handling, prompt-injection mitigations, output filters, blocked topics per assistant. |
| Content safety | Provider moderation hooks + local policy layers. |

### Module 7 — Observability, audit, and compliance

| Topic | Outcomes / capabilities |
|--------|---------------------------|
| Tracing | End-to-end traces for chat, retrieval, tool calls (e.g. Langfuse-class). **(Chunk 6 optional)** |
| Audit logs | Who invoked what, which assistant, which API key; retention and export. **(MVP: conversation/message persistence)** |
| Application metrics | Latency, errors, queue depth, ingestion backlog, saturation. |
| Security monitoring | Failed auth, abuse patterns, anomaly alerts. |
| Data residency & retention | Configurable retention, deletion, backup/restore story for embeddings and logs. |

### Module 8 — Platform engineering and delivery

| Topic | Outcomes / capabilities |
|--------|---------------------------|
| Container runtime | Docker images, health checks, graceful shutdown. **(MVP: Compose)** |
| Orchestration | Kubernetes manifests/Helm, HPA, pod disruption budgets. |
| Infrastructure as code | Terraform/OpenTofu for cloud or on-prem dependencies (LB, DB, object storage). |
| CI/CD | Lint, test, build, migrate, deploy across **dev / test / staging / prod**; rollback strategy. **(Chunk 7 starter)** |
| Secrets management | Vault/KMS integration; rotation runbooks. |
| Object storage | Durable file store for uploads (S3-compatible, Azure Blob, MinIO). **(MVP: local volume acceptable)** |

### Module 9 — Documentation, support, and operations

| Topic | Outcomes / capabilities |
|--------|---------------------------|
| Runbooks | Incidents, scaling, key rotation, model upgrades, reindex. |
| User documentation | Non-technical guides; acceptable use; data handling. |
| Developer documentation | OpenAPI, assistant schema, embedding/RAG contracts. |
| Support tiers | L1 triage playbook, L2/L3 escalation, log locations, known issues. |

### Syllabus → plan coverage map

| Module | In MVP chunks below? |
|--------|----------------------|
| 1 — Product UX | Partial: assistant catalog + **conversation** chat shell (order per [chat spec](../specs/2026-03-22-chat-conversations-design.md)); onboarding/training/FAQ later |
| 2 — Identity & access | Partial: dev bearer today; **Microsoft Entra** per [auth spec](../specs/2026-03-22-auth-entra-design.md); RBAC/ACL; SAML/SCIM later |
| 3 — APIs & lifecycle | Partial: assistant CRUD + chat API; versioning + public API keys later |
| 4 — FinOps | Partial: logging foundation; LiteLLM/budgets later |
| 5 — RAG | Partial: upload → embed → retrieve; OCR/connectors/evals later |
| 6 — Agents & safety | Later (or thin guardrails only) |
| 7 — Observability | Partial: logs/conversations; full traces/metrics later |
| 8 — Platform | Partial: Compose + CI; K8s/Terraform later |
| 9 — Docs & ops | Ongoing (README first; runbooks as you harden) |

---

## File layout (greenfield)

| Path | Responsibility |
|------|----------------|
| `docker-compose.yml` | Postgres, Redis, api, worker, web, optional litellm/langfuse |
| `backend/pyproject.toml` | Python deps, ruff/pytest config |
| `backend/src/ai_portal/main.py` | FastAPI app factory |
| `backend/src/ai_portal/config.py` | Settings via `pydantic-settings` |
| `backend/src/ai_portal/db/` | Engine, session, base models |
| `backend/src/ai_portal/models/` | SQLAlchemy models |
| `backend/src/ai_portal/api/` | Routers: health, auth stub, assistants, chat, documents |
| `backend/src/ai_portal/services/` | LLM client, RAG retrieval, ingestion tasks |
| `backend/src/ai_portal/worker.py` | Celery app |
| `backend/tests/` | Pytest |
| `backend/alembic/` | Migrations |
| `frontend/` | Vite React app |
| `frontend/src/routes/` | TanStack Router routes |
| `frontend/src/api/` | Typed client to backend |
| `README.md` | How to run, env vars |

Files that change together: keep `models/` + `alembic` + API routers aligned per feature.

---

## Chunk 1: Repository skeleton and local infra

### Task 1: Docker Compose baseline

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `README.md`

- [ ] **Step 1:** Add services `postgres` (image with pgvector, e.g. `pgvector/pgvector:pg16`), `redis`, named volumes, healthchecks. Expose `5432` and `6379` only on localhost.

- [ ] **Step 2:** Document in `README.md`: copy `.env.example` → `.env`, run `docker compose up -d postgres redis`.

- [ ] **Step 3:** Commit (after `git init`): `chore: add compose for postgres and redis`

---

### Task 2: Backend package scaffold

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/ai_portal/__init__.py`
- Create: `backend/src/ai_portal/main.py`
- Create: `backend/src/ai_portal/config.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_health.py
from fastapi.testclient import TestClient
from ai_portal.main import app

def test_health_ok():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 2:** Run `cd backend && pip install -e ".[dev]" && pytest tests/test_health.py -v` — expect import/app errors until implemented.

- [ ] **Step 3: Minimal implementation**

`config.py`: load `DATABASE_URL`, `REDIS_URL` from env (optional defaults for local).

`main.py`: FastAPI app, `GET /health` returns `{"status":"ok"}`.

`pyproject.toml`: dependencies `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `httpx`; dev: `pytest`, `ruff`.

- [ ] **Step 4:** Run pytest — expect PASS.

- [ ] **Step 5:** Commit `feat(api): health endpoint and package scaffold`

---

### Task 3: DB session and Alembic

**Files:**
- Create: `backend/src/ai_portal/db/session.py`
- Create: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/001_initial.py`
- Modify: `backend/src/ai_portal/config.py`

- [ ] **Step 1:** Add SQLAlchemy 2 async or sync engine (pick one and stay consistent; sync + `psycopg` is simpler for MVP).

- [ ] **Step 2:** Wire Alembic to metadata; first migration enables `vector` extension and creates placeholder if needed.

- [ ] **Step 3:** Document: `alembic upgrade head` in README.

- [ ] **Step 4:** Commit `feat(db): sqlalchemy session and alembic`

---

## Chunk 2: Core domain — users, roles, assistants

### Task 4: User and Assistant models + RBAC tables

**Files:**
- Create: `backend/src/ai_portal/models/user.py`
- Create: `backend/src/ai_portal/models/assistant.py`
- Create: `backend/src/ai_portal/models/role.py`
- Create: `backend/src/ai_portal/models/__init__.py`
- Create: `backend/alembic/versions/002_core_catalog.py`
- Create: `backend/tests/test_models_smoke.py`

**Model sketch (adjust types in migration):**
- `users`: id, email unique, hashed_password nullable (if SSO later), created_at
- `roles`: id, name (e.g. `admin`, `member`)
- `user_roles`: user_id, role_id
- `assistants`: id, name, description, system_prompt, owner_user_id, visibility (`private`/`org`), created_at
- `assistant_acl`: assistant_id, user_id OR role_id (MVP: user_id only is simpler)

- [ ] **Step 1:** Migration creates tables; test inserts one user and one assistant via SQLAlchemy session.

- [ ] **Step 2:** Commit `feat(models): users roles assistants acl`

---

### Task 5: Assistant catalog API

**Files:**
- Create: `backend/src/ai_portal/api/deps.py` (get_db, get_current_user stub)
- Create: `backend/src/ai_portal/api/assistants.py`
- Modify: `backend/src/ai_portal/main.py` (include router)
- Create: `backend/tests/test_assistants_api.py`

- [ ] **Step 1: Failing test** — `GET /api/assistants` returns 401 without auth.

- [ ] **Step 2:** Implement stub auth: `Authorization: Bearer devtoken` maps to seed user (config `DEV_SEED_USER_EMAIL`) for local dev only.

- [ ] **Step 3:** `GET /api/assistants` lists assistants visible to user (owner or ACL).

- [ ] **Step 4:** `POST /api/assistants` creates assistant (member+).

- [ ] **Step 5:** pytest + commit `feat(api): assistant catalog with dev auth`

---

## Chunk 3: Chat and model gateway

### Task 6: Chat completions service

**Files:**
- Create: `backend/src/ai_portal/services/llm.py`
- Create: `backend/src/ai_portal/api/chat.py`
- Create: `backend/tests/test_chat_api.py`

- [ ] **Step 1:** Config: `OPENAI_API_BASE`, `OPENAI_API_KEY` (point to LiteLLM proxy or OpenAI-compatible endpoint).

- [ ] **Step 2:** `POST /api/chat` body: `{ assistant_id, messages: [{role, content}] }` — load assistant, apply system prompt, call chat completions API via `httpx`.

- [ ] **Step 3:** Persist `chat_sessions` and `chat_messages` (add migration) minimally for audit.

- [ ] **Step 4:** Test with mocked `httpx` response.

- [ ] **Step 5:** Commit `feat(chat): openai-compatible chat with session logging`

---

### Task 7 (optional in MVP): LiteLLM sidecar

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

- [ ] Add `litellm` service; document routing all model calls through it for future per-key budgets.

---

## Chunk 4: RAG pipeline (minimal)

### Task 8: Documents and chunks

**Files:**
- Create: `backend/src/ai_portal/models/document.py`
- Create: `backend/alembic/versions/003_rag.py`
- Create: `backend/src/ai_portal/services/embedding.py`
- Create: `backend/src/ai_portal/worker.py` (Celery)
- Create: `backend/src/ai_portal/tasks/ingest.py`

- [ ] **Step 1:** Tables: `documents` (id, assistant_id, filename, storage_path, status), `document_chunks` (id, document_id, content, embedding vector, meta json).

- [ ] **Step 2:** API `POST /api/assistants/{id}/documents` multipart upload → store file → enqueue Celery task.

- [ ] **Step 3:** Task: extract text (MVP: plain text / pypdf only), chunk, embed via same OpenAI-compatible embeddings API, insert rows.

- [ ] **Step 4:** `docker-compose` services `api` and `worker` with shared env; worker depends on redis.

- [ ] **Step 5:** Commit `feat(rag): upload ingest and chunk embeddings`

---

### Task 9: Retrieval-augmented chat

**Files:**
- Modify: `backend/src/ai_portal/api/chat.py`
- Modify: `backend/src/ai_portal/services/rag.py`
- Create: `backend/tests/test_rag_retrieval.py`

- [ ] **Step 1:** On chat, embed last user message, `pgvector` similarity search scoped to assistant’s documents, inject top-k into system or tool message.

- [ ] **Step 2:** Test retrieval with fixed embeddings (mock or small fixture).

- [ ] **Step 3:** Commit `feat(rag): retrieval injection into chat`

---

## Chunk 5: Frontend portal

### Task 10: Vite React app and API client

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`
- Create: `frontend/src/main.tsx`, `frontend/src/router.tsx`
- Create: `frontend/src/api/client.ts`

- [ ] **Step 1:** TanStack Router routes: `/` catalog list, `/assistants/:id` chat UI (minimal).

- [ ] **Step 2:** Read `VITE_API_BASE_URL`; attach `Authorization` header from env `VITE_DEV_TOKEN` for MVP.

- [ ] **Step 3:** Commit `feat(web): catalog and chat shell`

---

### Task 11: Dockerize web + api

**Files:**
- Create: `backend/Dockerfile`, `frontend/Dockerfile`
- Modify: `docker-compose.yml`

- [ ] **Step 1:** Multi-stage builds; compose profiles for full stack.

- [ ] **Step 2:** README one-command `docker compose up --build`.

- [ ] **Step 3:** Commit `chore: dockerfiles for api and web`

---

## Chunk 6: Observability and hardening (post-MVP slice)

### Task 12: Structured logging and request IDs

**Files:**
- Modify: `backend/src/ai_portal/main.py`
- Create: `backend/src/ai_portal/logging.py`

- [ ] Add JSON logs, `X-Request-ID` propagation.

---

### Task 13: Langfuse (optional)

**Files:**
- Modify: `docker-compose.yml`
- Modify: `backend/src/ai_portal/services/llm.py`

- [ ] Trace generations if `LANGFUSE_*` env set.

---

## Chunk 7: CI and quality gates

### Task 14: GitHub Actions (or local scripts)

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1:** Job: `ruff check`, `pytest`, `npm ci && npm run build` on push.

- [ ] **Step 2:** Commit `ci: backend and frontend checks`

---

## Plan review checklist (manual)

- [ ] Every chunk produces runnable software (Compose + migrations + tests).
- [ ] No secrets in repo; `.env.example` only placeholders.
- [ ] YAGNI: defer SSO, billing, MCP servers, RAGAS suite until catalog+chat+RAG path works end-to-end.

---

**Plan complete and saved to `docs/superpowers/plans/2026-03-21-ai-portal-mvp-implementation.md`. Ready to execute?**

When executing, prefer @superpowers:executing-plans in this environment (single session) unless subagents are available.
