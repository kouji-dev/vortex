# Backend Clean Architecture Refactor

**Date:** 2026-04-07
**Scope:** Structure-only refactor — no logic changes, no behaviour changes, no new features.
**Goal:** Apply SRP + Clean Code principles to the Python backend using a domain-first, hybrid-hexagonal layout. Each domain becomes a self-contained module with clear layer contracts.

---

## Decisions

| Question | Decision |
|---|---|
| Architecture style | Hybrid hexagonal — Protocol interfaces only at volatile external boundaries (LLM, embedding). Plain classes everywhere else. |
| Module organisation | Domain-first — top level = domains, layers live inside each domain. |
| Background workers | Absorbed into their owning domain under a `workers/` subfolder. |
| RAG | Own domain (`rag/`) — shared by `chat` and `knowledge_base`, knows nothing about either. |
| ORM models | Stay flat in `models/` — they are already thin and don't benefit from domain grouping. |

---

## Target Folder Structure

```
src/ai_portal/
├── chat/
│   ├── __init__.py
│   ├── router.py          ← FastAPI routes (thin controller)
│   ├── service.py         ← streaming, history, starters, tool orchestration
│   ├── repository.py      ← DB queries: conversations, messages, KB links
│   ├── schemas.py         ← Pydantic request/response/internal DTOs
│   └── workers/
│       └── memory/
│           ├── __init__.py
│           ├── extractor.py
│           └── summarizer.py
│
├── knowledge_base/
│   ├── __init__.py
│   ├── router.py
│   ├── service.py         ← KB CRUD, document management, connector logic
│   ├── repository.py      ← DB queries: KBs, documents, chunks, connectors
│   ├── schemas.py
│   └── workers/
│       └── ingest/
│           ├── __init__.py
│           ├── worker.py
│           ├── job.py
│           ├── chunking.py
│           ├── readers.py
│           └── progress.py
│
├── catalog/
│   ├── __init__.py
│   ├── router.py          ← model catalog endpoints
│   ├── service.py         ← model access, validation, default resolution
│   ├── repository.py      ← DB queries: catalog_models
│   ├── schemas.py
│   ├── definitions.py     ← moved from catalog_model_definitions.py (root)
│   ├── specs.py           ← moved from catalog_specs.py (root)
│   └── providers/
│       ├── __init__.py
│       ├── protocol.py    ← LLMProvider Protocol interface
│       ├── langchain.py   ← concrete LangChain impl
│       └── routing.py     ← model routing logic
│
├── auth/
│   ├── __init__.py
│   ├── router.py          ← login, token refresh, setup endpoints
│   ├── service.py         ← user identity, upsert from claims
│   ├── repository.py      ← DB queries: users, orgs, invites, portal API keys
│   ├── schemas.py
│   ├── deps.py            ← get_current_user, get_current_org_id (moved from api/deps.py)
│   └── strategies/
│       ├── __init__.py
│       ├── dev.py
│       ├── entra.py
│       ├── jwt.py
│       └── portal_keys.py
│
├── rag/
│   ├── __init__.py
│   ├── service.py         ← retrieval logic (moved from services/rag.py)
│   ├── protocols.py       ← EmbeddingProvider Protocol interface
│   └── providers/
│       ├── __init__.py
│       └── voyage.py      ← concrete Voyage embedding impl
│
├── tools/                 ← largely unchanged, already well-structured
│   ├── __init__.py
│   ├── registry.py
│   ├── search/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── duckduckgo.py
│   │   └── tavily.py
│   └── data/
│       ├── __init__.py
│       └── query.py
│
├── models/                ← SQLAlchemy ORM models (kept flat, unchanged)
│   ├── __init__.py
│   ├── assistant.py
│   ├── catalog_model.py
│   ├── chat.py
│   ├── connector.py
│   ├── document.py
│   ├── knowledge_base.py
│   ├── memory.py
│   ├── org.py
│   ├── org_invite.py
│   ├── user.py
│   └── user_portal_api_key.py
│
├── core/                  ← shared infrastructure
│   ├── __init__.py
│   ├── config.py          ← get_settings() (moved from root)
│   ├── logging.py         ← moved from logging_config.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── session.py
│   │   ├── base.py
│   │   └── types.py
│   └── middleware/
│       ├── __init__.py
│       └── setup_guard.py
│
├── scripts/               ← unchanged
│   ├── run_ingest_worker.py
│   └── seed_catalog_models.py
│
└── main.py                ← mounts all domain routers
```

---

## Layer Contracts

These rules apply inside every domain. They are the heart of the refactor.

### router.py — Controller
- Owns FastAPI route decorators and path definitions
- Parses and validates HTTP request via Pydantic schemas
- Calls service methods — passes domain primitives, not ORM models or raw DB sessions
- Returns Pydantic response schemas
- **Never:** touches SQLAlchemy directly, contains business logic, raises domain errors as HTTP exceptions (the service raises `ValueError`/custom exceptions; the router maps them to HTTP)

### service.py — Service
- Contains all business logic for the domain
- Receives a `Session` via dependency injection (FastAPI `Depends`) and calls its own repository
- May call services from other domains (e.g. `chat.service` calls `rag.service`)
- **Never:** imports from `fastapi`, knows about HTTP status codes, constructs `HTTPException`

### repository.py — Repository
- Contains all SQLAlchemy queries for the domain
- Methods accept a `Session` and return ORM model instances or plain Python types
- No business logic — pure data access
- **Never:** calls other repositories directly (go through the service layer)

### schemas.py — Schemas
- All Pydantic models for this domain: request bodies, response models, internal DTOs
- Kept in one file per domain unless the file exceeds ~200 lines, in which case split into `schemas/` subfolder
- **Never:** imports ORM models (use `model_config = {"from_attributes": True}` for ORM → schema conversion at the boundary)

---

## Protocol Interfaces (Hybrid Hexagonal)

Only two boundaries get Protocol interfaces — the ones that are volatile or need mocking in tests:

### `catalog/providers/protocol.py` — LLMProvider
```python
from typing import Any, Iterator, Protocol

class LLMProvider(Protocol):
    def stream_deltas(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> Iterator[str]: ...

    def stream_deltas_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[dict[str, Any]]: ...
```

### `rag/protocols.py` — EmbeddingProvider
```python
from typing import Protocol

class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
    def embeddings_missing_key_message(self) -> str: ...
```

Everything else (repositories, services, auth strategies) uses plain concrete classes — no unnecessary abstraction.

---

## Key Migrations

| Before | After | Reason |
|---|---|---|
| `api/conversations.py` (1145 lines) | `chat/router.py` + `service.py` + `repository.py` + `schemas.py` | SRP — one file, one concern |
| `api/knowledge_bases.py` (600 lines) | `knowledge_base/router.py` + `service.py` + `repository.py` + `schemas.py` | Same |
| `api/deps.py` | `auth/deps.py` | Auth concern belongs in auth domain |
| `catalog_model_definitions.py` (root) | `catalog/definitions.py` | Orphaned file moved to owning domain |
| `catalog_specs.py` (root) | `catalog/specs.py` | Same |
| `services/rag.py` (363 lines) | `rag/service.py` | RAG is a domain, not a service utility |
| `services/embedding.py` | `rag/providers/voyage.py` + `rag/protocols.py` | Concrete impl + Protocol separation |
| `services/llm.py` + `llm_connect.py` | `catalog/providers/routing.py` + `langchain.py` | LLM concerns belong in catalog |
| `services/conversation_model_resolve.py` | `catalog/service.py` | Model resolution is a catalog concern |
| `services/default_conversation_model.py` | `catalog/service.py` | Same |
| `services/user_identity.py` | `auth/service.py` | Auth concern |
| `services/portal_api_keys.py` | `auth/strategies/portal_keys.py` | Auth concern |
| `services/model_access.py` | `catalog/service.py` | Catalog concern |
| `services/catalog_model_validate.py` | `catalog/service.py` | Catalog concern |
| `services/ingest_queue.py` | `knowledge_base/service.py` | KB concern |
| `workers/ingest/` | `knowledge_base/workers/ingest/` | Domain ownership |
| `workers/memory/` | `chat/workers/memory/` | Domain ownership |
| `tasks/ingest.py` | `knowledge_base/workers/ingest/tasks.py` | Domain ownership |
| `tasks/connector_jobs.py` | `knowledge_base/workers/` | Domain ownership |
| `auth/` (entra, jwt, manager, password) | `auth/strategies/` | Clear strategy pattern |
| `logging_config.py` | `core/logging.py` | Infrastructure concern |
| `config.py` | `core/config.py` | Infrastructure concern |
| `db/` | `core/db/` | Infrastructure concern |
| `middleware/` | `core/middleware/` | Infrastructure concern |

---

## What Does NOT Change

- All SQLAlchemy ORM models in `models/` — kept flat, no changes to schema
- All Alembic migrations
- All business logic, algorithms, and streaming behaviour
- The `tools/` module structure (already well-organised)
- The `scripts/` folder
- Any external API contract (URLs, request/response shapes)
- Tests — updated only to reflect new import paths

---

## Implementation Approach

This refactor is pure file movement + import path updates. The recommended approach:

1. **One domain at a time** — complete `chat/`, verify imports, then move to `knowledge_base/`, etc.
2. **`core/` first** — move `config.py`, `db/`, `logging_config.py`, `middleware/` before touching domains (everything imports from these)
3. **Temporary re-exports** — during migration, add `from ai_portal.chat.router import router` shims in old locations to keep the app running while migrating incrementally
4. **Run tests after each domain** — `pnpm test:e2e:filter <domain>` to verify no regressions

Estimated domain order:
1. `core/` — shared infra (no dependencies on other domains)
2. `rag/` — no domain dependencies
3. `tools/` — minimal changes
4. `catalog/` — depends on `core/`
5. `auth/` — depends on `core/`
6. `knowledge_base/` — depends on `core/`, `rag/`
7. `chat/` — depends on everything (last, most complex)
