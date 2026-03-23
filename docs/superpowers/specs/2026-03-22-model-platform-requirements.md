# Model platform — actionable delivery spec

**Document type:** implementation-oriented tasks + baseline inventory (normative **SHALL** ids in [Appendix A](#appendix-a-normative-requirement-ids))  
**Status:** spec-draft  
**Date:** 2026-03-22  

**Architecture:** [LLM access & model governance design](./2026-03-22-llm-access-model-governance-design.md)  
**Related:** [Auth & Entra](./2026-03-22-auth-entra-design.md), [Chat conversations](./2026-03-22-chat-conversations-design.md)

---

## How to use this doc

1. **Ship in vertical slices** — Prefer one workstream (or a thin cut across WS-C → WS-E) per EPIC rather than schema-only tickets that block the UI.  
2. **Check off tasks** in git/PM tool; keep this file or the board as the source of truth.  
3. **Appendix A** remains the audit trail for **REQ-*** SHALL language.

### Metadata rule (non-negotiable)

**Product-facing metadata** (model catalog fields, effort, display copy, request-access configuration, catalog-level defaults, per-user model settings, grant records, etc.) **must live in PostgreSQL** and **must be read/written through HTTP APIs** (authenticated; admin routes where appropriate). Clients **must not** depend on hard-coded model lists or entitlement state in the SPA bundle. **Environment variables** remain for **secrets** and **deployment topology** (e.g. `LLM_API_KEY`, base URL)—not as the source of truth for catalog or access metadata.

---

## 1. Existing baseline (already in repo)

Use this as the starting line before picking up new tasks.

| Area | What exists today |
|------|-------------------|
| **LiteLLM in-process** | `litellm.completion` / streaming in `services/llm_providers/litellm_chat.py`; `litellm.embedding` in `services/embedding.py`. |
| **Vendor-neutral config** | `LLM_API_BASE` / `LLM_API_KEY` (aliases `OPENAI_*`) in `config.py`; `normalize_openai_compatible_base` in `services/llm_connect.py`. |
| **Model string resolution (minimal)** | `services/model_access.effective_chat_model()` = `CHAT_MODEL` or per-request override only — **no catalog, no grants**. |
| **Portal API keys** | `UserPortalApiKey` + migration `009`; `POST/GET/DELETE /api/me/portal-api-keys`; `aip_…` resolved in `deps.get_current_user` before dev/Entra JWT. |
| **Human auth** | Dev bearer + Entra JWT per auth spec. |
| **RAG** | Documents/chunks/embeddings in app + Postgres; ingest uses `embed_texts`. |
| **Chat** | Legacy `/api/chat` + conversations API with `model` on conversation/body; **no** catalog list, **no** entitlement enforcement, **no** per-model settings API. |
| **Observability / cost** | No structured usage/cost capture on LLM calls yet. |
| **Catalog metadata in DB/API** | Not yet — model choice is env + `CHAT_MODEL` / conversation string, not a persisted catalog API. |

---

## 2. Workstreams & tasks

### WS-PLAT — Platform & LiteLLM alignment (REQ-PLAT-*)

**Goal:** Keep invocation in-app; no production coupling to LiteLLM proxy; RAG boundaries unchanged.

| # | Task | Covers |
|---|------|--------|
| PLAT-01 | Document in `README` / runbooks: production **does not** rely on LiteLLM HTTP proxy; optional Compose `litellm` is dev-only. | REQ-PLAT-01 |
| PLAT-02 | Add **architecture decision record** or comment in `docker-compose` that vendor keys are app-injected, not Azure-specific code paths. | REQ-PLAT-02 |
| PLAT-03 | Verify all LLM calls go through **one** module boundary (`llm.py` + provider) so future catalog resolution plugs in once. Refactor only if duplicated entry points appear. | REQ-PLAT-01, REQ-PLAT-04 |
| PLAT-04 | Confirm RAG paths (`documents`, `ingest`, `rag` svc) do **not** move ACLs into LiteLLM; add a one-line guard comment if useful. | REQ-PLAT-05 |

**Done when:** Docs + code entry points match design; no new vendor `if azure:` branches.

---

### WS-AUTH — Portal keys & identity hardening (REQ-AUTH-*, REQ-NFR-*)

**Goal:** Agent auth is production-safe; aligns with Entra for humans.

| # | Task | Covers |
|---|------|--------|
| AUTH-01 | **Require** `PORTAL_API_KEY_PEPPER` in non-dev deploy docs; fail fast or warn loudly if empty in `entra` mode. | REQ-NFR-02 |
| AUTH-02 | Security review: document threat model for stolen `aip_` keys (revocation, rotation, `last_used_at` monitoring). | REQ-AUTH-03–05 |
| AUTH-03 | Optional: add **scopes** or labels on keys (`ingest_only`, `chat_only`) if product needs least privilege before GA. | Future |

**Done when:** Ops runbook + pepper policy; existing create/list/revoke flows covered by tests (`test_portal_api_keys.py`).

---

### WS-CAT — Model catalog & listing API (REQ-CAT-*, REQ-META-*)

**Goal:** Persistent catalog with **effort**; API returns **all** models + accessibility + request-access hook. **All** catalog metadata columns (including extensible fields) are **DB-backed** and **serialized in API** responses; admin writes round-trip through the API.

| # | Task | Covers |
|---|------|--------|
| CAT-01 | Add **`catalog_models`** (name TBD) table: internal `id`, `slug`, `display_name`, `description`, `litellm_model_id`, `effort` enum (`default`/`low`/`medium`/`high`), `is_active`, `sort_order`, timestamps; optional **`metadata` JSONB** (or explicit columns) for extra UI/ops fields—**no** orphan keys only in frontend. | REQ-CAT-01, REQ-META-01 |
| CAT-02 | Seed migration or admin script: initial rows mirroring current `CHAT_MODEL` / `EMBEDDING_MODEL` behavior for backward compatibility. | REQ-CAT-05 |
| CAT-03 | **`GET /api/models`** (or under `/api/chat/...`): returns **full** active catalog; each row includes `accessible: bool` (stub `true` for all authenticated users in MVP slice if grants not ready). **Every** persisted catalog field intended for clients **must** appear in this schema (or nested `metadata` object). | REQ-CAT-02, REQ-CAT-03, REQ-META-02 |
| CAT-04 | Add response fields: `can_request_access: bool`, `request_access_url` or `request_workflow_id` nullable — **store** configurable values in DB (per row or tenant defaults table), not only constants in code. | REQ-CAT-04, REQ-META-01 |
| CAT-05 | **Admin API** (`POST/PATCH`): create/update/disable catalog rows + metadata; validate with Pydantic; **OpenAPI** documents all writable fields. | REQ-CAT-05, REQ-META-02 |
| CAT-06 | **Frontend:** model picker **fetches** list from API only; locked models visible with CTA “Request access” using API-provided flags/URLs. | REQ-CAT-02–04, REQ-META-02 |
| CAT-07 | Integration tests: create catalog row via admin API → assert `GET /api/models` returns identical metadata. | REQ-META-01–02 |

**Done when:** UI can show locked + unlocked; OpenAPI documents shape; Postgres is source of catalog; no catalog metadata exists only in env or static frontend.

---

### WS-ENT — Grants & resolution (REQ-ENT-*)

**Goal:** No LiteLLM call until entitlement check passes.

| # | Task | Covers |
|---|------|--------|
| ENT-01 | Decide **grant subject**: `user_id`, `team_id`, or both; add `team` (or org) table if missing — smallest model that matches product. | REQ-ENT-01 |
| ENT-02 | Add **`model_grants`** (subject → `catalog_model_id`); migration + unique constraint. **Expose** effective grants to authorized callers via API if product needs “why am I locked?” (read-only); grants remain DB source of truth. | REQ-ENT-01, REQ-META-01, REQ-META-02 |
| ENT-03 | Implement **`resolve_model_for_request(user, team?, catalog_model_id|slug)`** → LiteLLM string or raise `Forbidden`; replace direct `effective_chat_model` usage in chat/conversation paths. | REQ-ENT-02, REQ-ENT-03, REQ-PLAT-04 |
| ENT-04 | Wire **`GET /api/models`**: `accessible` from grants (not stub). | REQ-CAT-03 |
| ENT-05 | On denied chat/stream: **403** + structured log (no upstream call). | REQ-ENT-03, REQ-OBS-02 |
| ENT-06 | **Fallback** (REQ-ENT-04): product workshop → document ordered fallbacks + error triggers → implement in resolver + tests. | REQ-ENT-04 |

**Done when:** Changing grants changes who can chat without redeploy; denied requests never hit LiteLLM.

---

### WS-CHAT — Per-model settings (REQ-CHAT-*)

**Goal:** Temperature + system prompt override per user (or per conversation) for **accessible** models only.

| # | Task | Covers |
|---|------|--------|
| CHAT-01 | Schema: e.g. `user_model_settings(user_id, catalog_model_id, temperature, system_prompt_override, …)` with uniqueness on (user, model). | REQ-CHAT-01 |
| CHAT-02 | **`GET/PATCH /api/me/model-settings/{catalog_model_id}`** (or nested under conversations): 403 if model not accessible; **GET** returns all persisted settings fields (no silent defaults only in UI). | REQ-CHAT-01, REQ-CHAT-02, REQ-META-02 |
| CHAT-03 | Document **merge order** in code comment + spec: global default → catalog default → user override → conversation override (adjust to chat spec). | REQ-CHAT-03 |
| CHAT-04 | Pass merged **`temperature`** and **system message** into `litellm.completion`; use `drop_params=True` or explicit handling when provider rejects temperature. | REQ-CHAT-04 |
| CHAT-05 | **Frontend:** settings panel for selected model; persist via API. | REQ-CHAT-01 |
| CHAT-06 | **Future spike:** MCP/tools flags on same row or JSONB; no MVP closure required. | REQ-CHAT-05 |

**Done when:** E2E: change temperature → next message reflects behavior; unauthorized model returns 403 on settings API.

---

### WS-OBS — Observability & cost (REQ-OBS-*)

**Goal:** Every success path emits usage + optional cost with portal dimensions.

| # | Task | Covers |
|---|------|--------|
| OBS-01 | Extract **usage** from LiteLLM / response (`usage.prompt_tokens`, `completion_tokens`, embedding totals) in a single helper used by chat + embedding. | REQ-OBS-03 |
| OBS-02 | Add **structured log** (JSON) or OpenTelemetry span attributes: `user_id`, `catalog_model_id` (or slug), `conversation_id` if any, `request_id`, token counts. | REQ-OBS-01, REQ-OBS-03 |
| OBS-03 | **Cost:** read LiteLLM `_hidden_params` / response cost if present; else optional **`model_pricing`** table (catalog_model_id, per-1k-in/out); compute estimated USD. | REQ-OBS-04 |
| OBS-04 | Choose **sink**: start with structured logs + optional `llm_usage_events` table for SQL rollups (FinOps). | REQ-OBS-05 |
| OBS-05 | Denied model attempts: log **without** PII secrets (REQ-OBS-02) with same `request_id`. | REQ-OBS-02 |
| OBS-06 | Dashboard or export query (document in runbook) aggregating by user / model / day. | REQ-OBS-05 |

**Done when:** Sample trace shows tokens + optional cost; SQL or log query can sum by `catalog_model_id` and user.

---

### WS-NFR — Cross-cutting

| # | Task | Covers |
|---|------|--------|
| NFR-01 | OpenAPI + integration tests for all new routes; enforce auth same as existing chat routes. | REQ-NFR-01 |
| NFR-02 | Load test or document max QPS for `last_used_at` update on portal keys (debounce if needed). | REQ-AUTH-* |

---

## 3. Suggested delivery order

1. **WS-CAT** (schema + list API + stub accessibility) — unblocks UI.  
2. **WS-ENT** (grants + resolver + wire chat) — satisfies security SHALL.  
3. **WS-CHAT** (settings + merge + LiteLLM params).  
4. **WS-OBS** (usage + cost + events table).  
5. **WS-AUTH** / **WS-PLAT** hardening in parallel early if deploying agents widely.

---

## Appendix A — Normative requirement IDs

The following **SHALL** statements are the compliance checklist. Implementation tasks above map to them.

### Definitions

| Term | Meaning |
|------|---------|
| **Catalog model** | Row in portal model catalog: id, **DB-persisted** metadata fields, LiteLLM model string, effort. |
| **Accessible model** | Catalog model the user may invoke given grants/context. |
| **Portal API key** | `aip_…` bearer key; hashed at rest. |
| **Effort** | `default` \| `low` \| `medium` \| `high` on catalog. |

### REQ-PLAT (platform)

| ID | SHALL |
|----|--------|
| REQ-PLAT-01 | Invoke LiteLLM from FastAPI (library); production does not depend on LiteLLM HTTP proxy for routing. |
| REQ-PLAT-02 | No vendor-specific control flow in core domain logic. |
| REQ-PLAT-03 | Upstream credentials from configurable secrets, not hard-coded. |
| REQ-PLAT-04 | Authorize catalog model use in portal before LiteLLM. |
| REQ-PLAT-05 | RAG corpus/ACLs in portal/Postgres; LiteLLM only for invocation shape. |

### REQ-AUTH (authentication)

| ID | SHALL |
|----|--------|
| REQ-AUTH-01 | Interactive users: OAuth2/OIDC (Entra per auth spec). |
| REQ-AUTH-02 | Support portal API keys as `Authorization: Bearer`. |
| REQ-AUTH-03 | Keys resolve to one user; hash at rest. |
| REQ-AUTH-04 | Create / list (masked) / revoke keys via API. |
| REQ-AUTH-05 | Revoked keys rejected; no model calls. |

### REQ-CAT (catalog & listing)

| ID | SHALL |
|----|--------|
| REQ-CAT-01 | Persistent catalog with effort and LiteLLM model string. |
| REQ-CAT-02 | List endpoint returns all relevant catalog models, not only accessible. |
| REQ-CAT-03 | Each entry includes accessibility for current principal/context. |
| REQ-CAT-04 | Non-accessible entries support “request access” in API shape. |
| REQ-CAT-05 | Admins can manage catalog without code deploy where policy allows. |

### REQ-META (metadata: database + API)

| ID | SHALL |
|----|--------|
| REQ-META-01 | Product-visible **model/catalog metadata** (display fields, effort, request-access configuration, catalog defaults, grant rows, user model settings, etc.) **SHALL** be **persisted in PostgreSQL** (or the primary app database), not only in environment variables, static frontend bundles, or LiteLLM config files. |
| REQ-META-02 | Clients **SHALL** obtain and update that metadata through **documented HTTP APIs** (read paths at minimum; writes via admin or user settings endpoints as appropriate). Secrets and deployment topology **MAY** remain in env; they **SHALL NOT** be the sole store for catalog or entitlement metadata. |

### REQ-ENT (entitlements)

| ID | SHALL |
|----|--------|
| REQ-ENT-01 | Persist grants linking subject to catalog model. |
| REQ-ENT-02 | Resolution step before completion/streaming. |
| REQ-ENT-03 | No LiteLLM call if not entitled. |
| REQ-ENT-04 | Fallback policy in portal config (detail in follow-on). |

### REQ-CHAT (settings)

| ID | SHALL |
|----|--------|
| REQ-CHAT-01 | View/update temperature + system prompt for accessible models. |
| REQ-CHAT-02 | Settings API denied for non-accessible models. |
| REQ-CHAT-03 | Deterministic merge order for defaults/overrides. |
| REQ-CHAT-04 | Safe handling of unsupported provider params. |
| REQ-CHAT-05 | Extensible for MCP/tools (future). |

### REQ-OBS (observability & cost)

| ID | SHALL |
|----|--------|
| REQ-OBS-01 | Portal context on traces/logs (user, catalog model id, correlation id, team/org when defined). |
| REQ-OBS-02 | Log denied attempts without secrets. |
| REQ-OBS-03 | Capture input/output token usage on successful chat + embedding. |
| REQ-OBS-04 | Estimated cost when reliable; else usage only. |
| REQ-OBS-05 | Aggregatable by user, team/org, catalog model, time. |

### REQ-NFR

| ID | SHALL |
|----|--------|
| REQ-NFR-01 | New endpoints match existing auth/RBAC expectations. |
| REQ-NFR-02 | Sound random keys + HMAC/pepper hashing for portal keys. |

---

## Revision history

| Ver | Date | Summary |
|-----|------|---------|
| 0.1 | 2026-03-22 | Initial SHALL requirements |
| 0.2 | 2026-03-22 | REQ-OBS-03–05 cost/usage |
| **1.0** | **2026-03-22** | **Rewrote as actionable workstreams + baseline inventory; SHALLs moved to Appendix A** |
| 1.1 | 2026-03-22 | **Metadata rule:** DB + API for catalog/settings/grants; REQ-META-01–02; tasks CAT-07, ENT-02/CHAT-02 clarifications |
