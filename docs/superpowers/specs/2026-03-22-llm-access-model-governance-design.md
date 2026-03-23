# LLM access, model governance & LiteLLM integration

**Status:** spec-draft (design agreed in principle; fallback rules and schema TBD in implementation tickets)  
**Date:** 2026-03-22  
**Requirements & actionable tasks:** [Model platform delivery spec](./2026-03-22-model-platform-requirements.md) (Appendix A = SHALL ids)  
**Related:** [Auth & Entra](./2026-03-22-auth-entra-design.md) (OIDC for humans), [Chat conversations](./2026-03-22-chat-conversations-design.md)

---

## Product intent

Define how the AI Portal **calls language and embedding models** without coupling core code to a single cloud vendor (e.g. Azure-specific SDK paths). The portal **owns** org/team structure, **which models each team may use**, fallback policy, audit context, and **machine credentials** for agents. **LiteLLM** is used **from application code** to normalize multi-provider calls—not as the system of record for permissions.

**In scope (architecture)**

- In-process LiteLLM (`completion`, `embedding`, streaming) invoked by FastAPI services.
- Secrets (API keys, base URLs) loaded by the **app** from environment / Key Vault (or equivalent)—not hard-coded vendor branches in domain logic.
- Parallel authentication: **OAuth2/OIDC** (e.g. Entra JWT) for interactive users; **portal-issued API keys** (e.g. `aip_…` prefix) for tools without browser login (Codex, Claude Code, etc.), resolving to the same `users` row for authorization.
- Directional data model: **model catalog**, **team (or org) → model grants**, **resolution service** that returns an allowed LiteLLM model id or denies the request.

**Explicitly out of scope for this document**

- Running **LiteLLM as an HTTP proxy/gateway** as the primary integration pattern (optional dev compose services are not the product architecture).
- Delegating **product RBAC** or **team model entitlements** to LiteLLM Enterprise or any external gateway.
- Final schema migration details and exact fallback algorithms (captured in implementation plans once rules are chosen).

---

## Architecture

### Layering

| Layer | Responsibility |
|--------|----------------|
| **AI Portal (FastAPI + PostgreSQL)** | Identity linkage, org/team membership, **model allowlists**, conversation/resource ACLs, issuance and revocation of portal API keys, structured logging with business ids (`user_id`, `team_id`, `org_id`, internal `model_id`). |
| **LiteLLM (Python library)** | Uniform **invocation** of chat and embedding APIs across providers; streaming; reducing glue for provider-specific parameters. **Does not** decide who may call which model. |
| **Secrets & connectivity** | Upstream credentials and endpoints configured outside the repo and injected into the process; the app passes `api_key` / `api_base` (and similar) into LiteLLM as appropriate for the chosen route. |

### LiteLLM usage

- **Invoke LiteLLM from our code** (import and call in the API worker process).
- **Do not** rely on a separate LiteLLM proxy service for production routing; vendor normalization stays in the library layer.
- LiteLLM may still be used for **utilities** that simplify RAG-related work (e.g. consistent embedding calls) while **retrieval, chunking, vector storage, and document/assistant access control** remain in portal services and the database.

### Model governance (target shape)

Conceptual components (names may vary in implementation):

1. **Model catalog** — Stable internal identifier, display metadata, and the **LiteLLM model string** (e.g. `gpt-4o-mini`, `anthropic/claude-…`) used only **after** authorization. **Catalog and related product metadata live in the database and are exposed via HTTP APIs** (see [model platform delivery spec](./2026-03-22-model-platform-requirements.md), REQ-META).
2. **Entitlements** — Grants linking **team** (or org) to **allowed catalog entries**; optional limits (rate, tokens) can be added later.
3. **Resolution** — Given authenticated **user**, active **team** (when applicable), and requested logical model (or conversation default), either produce the **authorized** LiteLLM model string or return **403**. **Fallback** chains (ordered alternates, retry on specific HTTP errors, etc.) are defined in portal policy/tables—not by LiteLLM as product RBAC.

### Authentication summary

| Caller | Mechanism | Notes |
|--------|-----------|--------|
| **Human (browser / SPA)** | OIDC access token (e.g. Entra) as `Authorization: Bearer` | As specified in the Entra auth spec; app roles for coarse RBAC. |
| **Agent / CLI** | Portal API key (`aip_…`) as `Authorization: Bearer` | Hashed at rest; shown once at creation; revocable; resolves to `User` then same authorization path as other requests. |

### RAG

- **Corpus ownership, ingestion jobs, and pgvector search** are portal concerns.
- LiteLLM assists where it **reduces duplication** (e.g. embedding batch shape across providers); it does **not** replace document-level or assistant-level ACL checks.

### Observability

- Attach **portal** identifiers to traces and logs (user, team, org, internal model id, request id) in addition to anything LiteLLM emits, so FinOps and audit reports align with **your** tenancy model.
- Capture **usage** (tokens or equivalent) and **estimated cost** per successful invocation where possible; see [model platform requirements](./2026-03-22-model-platform-requirements.md) (REQ-OBS-03–05).

---

## Principles (non-goals)

- **No vendor-specific branches** in core business logic; a provider is configuration + LiteLLM model id, not a code fork.
- **Portal database + API** are authoritative for **who** may use **which** model; LiteLLM executes after that decision.
- **No production dependency** on LiteLLM running as a separate proxy for the above governance story.

---

## Open decisions (before implementation tickets)

1. **Fallback policy** — Per-catalog-model ordered fallbacks vs global defaults; which errors trigger retry vs hard fail.
2. **Team vs org** — Whether entitlements are keyed primarily by org, team, or both, and how the API selects “active team” for a request.
3. **Embedding route** — Same base URL/key as chat vs separate env vars when vendors differ (still portal-configured, not Azure-named code paths).

---

## Implementation note

Existing code may evolve toward this spec incrementally (config renames, removal of legacy provider switches, introduction of catalog tables). Treat this document as the **target architecture**; link EPICs and migrations to it when work starts.
