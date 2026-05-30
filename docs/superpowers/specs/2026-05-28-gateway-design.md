# Gateway — Design Spec

> **🚫 NO FAKE PROVIDER (shipping blocker).** Real LLM provider adapters must be built and wired through the facade; `FakeProvider` / `GATEWAY_USE_FAKE_PROVIDER` retired. Today the facade binds `FakeProvider` and there are **no real adapters under `gateway/providers/`** — building them (anthropic, openai, … as HTTP clients implementing `LLMProvider`) is the prerequisite for shipping. See suite-overview global directive.

## Purpose

- [ ] One audited, governed entry point for every LLM call inside an enterprise
- [ ] Drop-in replacement for OpenAI / Anthropic / Bedrock SDKs so existing tooling (Claude Code, Cursor, Continue, LangChain) works unmodified
- [ ] Buyer: CISO / Head of Platform Engineering
- [ ] Comparable to: llmgateway, LiteLLM, Portkey, Helicone — but with first-class enterprise control plane

## Module Boundary

### Owns

- [ ] `providers`, `provider_credentials` (per-org, encrypted)
- [ ] `models` (catalog: id, provider, capabilities, pricing)
- [ ] `model_aliases` (virtual names that route to physical models)
- [ ] `routing_policies` (per-org, ordered rule list)
- [ ] `rate_limit_rules`
- [ ] `prompt_cache_entries` (when not delegated to provider-native cache)
- [ ] `guardrail_policies`, `guardrail_violations`
- [ ] `request_traces` (one row per request, indexed by request_id)
- [ ] `playground_sessions`
- [ ] `model_evals`, `model_eval_runs`

### Consumes from Control Plane

- [ ] `require_actor` (every gateway call is authenticated)
- [ ] `require_permission` (per-route + per-model permissions)
- [ ] `emit_audit` (every request)
- [ ] `emit_usage` (tokens in/out/cache, cost)
- [ ] `emit_webhook` (policy violation, budget breach)
- [ ] `get_org_setting` (default routing policy, default guardrails)
- [ ] `is_module_enabled('gateway')`

### Exposed to other modules (internal contracts)

- [ ] `complete(request, actor) -> Response | AsyncIterator[Chunk]` — internal, bypasses HTTP, used by RAG/Memories/Workers
- [ ] `embed(texts, model, actor) -> Embeddings`
- [ ] `count_tokens(text, model) -> int`
- [ ] `estimate_cost(request, model) -> cents`

## Features — In Scope

### Provider-Compatible APIs

- [ ] OpenAI Chat Completions — `POST /v1/chat/completions` (streaming + non-streaming)
- [ ] OpenAI Embeddings — `POST /v1/embeddings`
- [ ] OpenAI Models — `GET /v1/models`
- [ ] OpenAI Moderations — `POST /v1/moderations`
- [ ] Anthropic Messages — `POST /v1/messages` (streaming + non-streaming + tool use + vision + thinking + caching)
- [ ] Anthropic Token-Count — `POST /v1/messages/count_tokens`
- [ ] Bedrock Converse — `POST /v1/converse` and `POST /v1/converse-stream`
- [ ] Each compatible surface lives behind a thin translation layer to an internal canonical request
- [ ] Request headers honored: `x-request-id`, `traceparent`, `anthropic-beta`, `openai-organization`

### Provider Catalog

- [ ] Built-in providers: `anthropic`, `openai`, `azure_openai`, `bedrock`, `vertex`, `gemini`, `mistral`, `ollama`, `vllm`, `together`, `groq`, `fireworks`
- [ ] Each provider declares: supported models, capabilities (vision, tools, thinking, cache, json_mode, streaming), pricing
- [ ] **Available provider SET + endpoint URLs declared in deployment config (YAML/env)** — admin CANNOT add or remove a provider, or change an endpoint, via the UI
- [ ] **Enable/disable a declared provider is a UI action** (within the config-declared set)
- [ ] **Model catalog declared in config**; per-model enable/disable in UI
- [ ] Provider credentials: deployment-level by default (see suite-overview deploy-vs-runtime split); per-org BYO-key is an open per-feature decision (current `provider_credentials` table is per-org)
- [ ] Health check per provider (probe `/models` or equivalent)
- [ ] Catalog refresh job (poll provider model lists daily)

### Model Aliases / Virtual Models

- [ ] Org admin defines aliases: `fast`, `smart`, `cheap`, `vision`, `coder`
- [ ] Alias resolves to a routing policy at request time
- [ ] Client SDK sends alias; server picks concrete model
- [ ] Pinning support: `model: "smart@2026-05-01"` freezes to a snapshot

### Routing & Failover

- [ ] Routing strategies: `static`, `priority_list`, `weighted`, `cost_optimized`, `latency_optimized`, `capability_match`
- [ ] Per-request override via header `x-gateway-routing-policy`
- [ ] Failover: if primary returns 5xx / rate-limited / timeout → next in list
- [ ] Retry policy per provider (max retries, backoff, jitter)
- [ ] Circuit breaker per provider/model (open after N consecutive failures, half-open probe)
- [ ] Routing decision recorded in trace

### Rate Limiting & Concurrency

Two distinct concerns — keep them separate.

**Inbound (tenant governance — configured *per API key*):**

- [ ] Limit dimensions: `RPM`, `TPM` (tokens per minute), `concurrent_requests`
- [ ] Configured as properties of an API key (see Control Plane → API Keys); resolvable up the hierarchy per-user / team / org / model
- [ ] Burst allowance (token bucket)
- [ ] 429 response with `Retry-After` header
- [ ] Limits visible in `GET /v1/limits/me`
- [ ] No standalone Rate Limits page — limits are edited inline when minting/editing an API key

**Outbound (provider-side resilience — automatic, no config surface):**

- [ ] Provider returns 429 / 5xx / timeout → backoff + retry + failover (see Routing & Failover)
- [ ] Circuit breaker per provider/model

### Prompt Caching

- [ ] Pass-through cache for Anthropic native prompt caching (5min + 1h tiers)
- [ ] Internal exact-match cache (request hash → response), opt-in per route
- [ ] Cache TTL configurable per policy
- [ ] Cache hit recorded in trace + usage event (`tokens_cache_read`)
- [ ] Cache backend abstraction (`cache/protocol.py`): in-memory (dev), Redis (prod), Postgres (no-Redis fallback)

### Tool Use / Function Calling

- [ ] Normalized internal representation
- [ ] Translates OpenAI `tools` ↔ Anthropic `tools` ↔ Bedrock `toolConfig`
- [ ] Parallel tool calls supported where provider supports them
- [ ] Tool response correlation (tool_use_id ↔ tool_result)

### Vision / Multimodal Inputs

- [ ] Image input normalized (base64 + URL)
- [ ] Per-provider size / format limits enforced before call
- [ ] PDF inputs normalized (Anthropic-native) — others fall back to extract-then-text

### Structured Outputs / JSON Mode

- [ ] OpenAI `response_format: json_schema` supported
- [ ] Anthropic tool-use trick supported for schema-constrained output
- [ ] Validation of returned JSON against schema (server-side, fail → retry-or-error policy)

### Embeddings

- [ ] `/v1/embeddings` OpenAI-compatible
- [ ] Multi-provider embedding routing (Voyage, OpenAI, Cohere, on-prem)
- [ ] Batch endpoint for bulk embedding (used internally by RAG ingest)
- [ ] Dimension reduction passthrough where provider supports

### Reranking (optional but bundled)

- [ ] `/v1/rerank` endpoint (Cohere-compatible)
- [ ] Providers: Voyage rerank, Cohere rerank, BGE-reranker (self-hosted)

### Moderation

- [ ] `/v1/moderations` endpoint
- [ ] Providers: OpenAI moderation, Anthropic categories (derived), self-hosted (LlamaGuard / ShieldGemma)

### Guardrails Pipeline

- [ ] Pre-call guardrails (on incoming prompt):
  - [ ] PII detection (entities + categories), action: `redact` / `block` / `flag`
  - [ ] Prompt injection detection (heuristics + classifier)
  - [ ] Topic deny / allow list
  - [ ] Custom regex / classifier plugin
  - [ ] Secret detection (API keys, JWTs, credit cards)
- [ ] Post-call guardrails (on response):
  - [ ] PII leakage check
  - [ ] Content moderation (hate, sexual, self-harm, violence)
  - [ ] Output schema validation
  - [ ] Custom regex / classifier plugin
- [ ] Policy bundle = ordered list of guardrails + action per failure
- [ ] Per-key / per-route / per-org policy assignment
- [ ] Violations written to `guardrail_violations`, audited, webhook
- [ ] Guardrail provider abstraction (`guardrails/protocol.py`)
- [ ] Bundled implementations: regex, presidio, openai_moderation, llamaguard, custom_classifier, semantic_router

### Cost & Budget Enforcement

- [ ] Per-request cost calculated using model catalog pricing
- [ ] Pre-call budget check (Control Plane budget API)
- [ ] Hard cutoff returns 402 Payment Required with explainer
- [ ] Cost included in response headers (`x-gateway-cost-cents`) and trace

### Observability

- [ ] `request_traces` row per call: latency, ttft, tokens, model, route, cache, guardrail outcomes, error
- [ ] OpenTelemetry export (traces + metrics)
- [ ] Metrics: `gateway_requests_total`, `gateway_request_duration_seconds`, `gateway_provider_errors_total`, `gateway_token_usage`, `gateway_cache_hits`
- [ ] Per-provider health + p50/p95/p99 latency dashboard
- [ ] Top spenders, top error sources, top cached prompts

### Playground (in-app)

- [ ] Test prompts against any configured model
- [ ] Side-by-side comparison (2–4 models)
- [ ] Save prompt to library
- [ ] Cost + latency shown per response

### Eval Framework

- [ ] Test set: list of `{input, expected, judge_model}` records
- [ ] Run a test set against N models → table of pass rate, latency, cost
- [ ] Judge types: exact match, regex, LLM-as-judge, custom
- [ ] Regression detection across runs

### Replay & Re-route

- [ ] Admin can re-run any historic request from trace viewer
- [ ] Optionally swap model / policy / guardrail bundle
- [ ] Re-run output diffed vs original

### Files API (proxy)

- [ ] `POST /v1/files` upload, `GET /v1/files/{id}`
- [ ] Backed by Control Plane `BlobStore`
- [ ] Used by Anthropic Files + OpenAI Assistants compatibility

## Features — Out of Scope (for now)

- [ ] Image generation (DALL-E / SDXL / Imagen)
- [ ] Audio generation (TTS / music)
- [ ] Realtime / voice APIs (WebRTC streaming)
- [ ] Fine-tuning APIs
- [ ] Batch API (delayed jobs)
- [ ] Assistants API stateful threads (chat module covers that separately)
- [ ] Vector store API (RAG module covers that)
- [ ] Semantic cache (embedding-based) — exact-match cache only for v1
- [ ] Multi-region active routing
- [ ] BYO-classifier upload UI (configs only via API for v1)
- [ ] WAF-level DDoS protection (delegated to deployment layer)
- [ ] Granular gateway RBAC beyond admin/member (custom per-feature gateway permissions) — deferred; admin-only panel for v1
- [ ] Member self-service read-only view (own usage + own keys) — deferred; see Access tiers above

## Configurable Abstractions

### LLM Provider

- [ ] Interface: `LLMProvider` with `complete`, `stream`, `embed`, `count_tokens`, `list_models`, `health`
- [ ] Capabilities declared per provider
- [ ] Bundled: `anthropic`, `openai`, `azure_openai`, `bedrock`, `vertex`, `gemini`, `mistral`, `ollama`, `vllm`
- [ ] **BLOCKER**: build the real adapters under `gateway/providers/` (HTTP clients implementing `LLMProvider`) and wire the facade to resolve them from credentials — none exist today; `FakeProvider` is the only implementation
- [ ] "How to add" template + checklist

### Routing Strategy

- [ ] Interface: `RoutingStrategy` with `pick(request, candidates, context) -> ProviderModel`
- [ ] Bundled: `static`, `priority`, `weighted`, `cost_optimized`, `latency_optimized`, `capability_match`, `custom_rules`

### Guardrail

- [ ] Interface: `Guardrail` with `check_input(prompt) -> Verdict`, `check_output(response) -> Verdict`
- [ ] Bundled: `regex`, `presidio`, `openai_moderation`, `llamaguard`, `prompt_injection_classifier`, `secret_scanner`, `topic_filter`, `schema_validator`

### Cache Backend

- [ ] Interface: `Cache` with `get`, `set`, `delete`
- [ ] Bundled: `inmemory`, `redis`, `postgres`

### Reranker (shared with RAG)

- [ ] Interface: `Reranker` with `rerank(query, docs, top_k)`
- [ ] Bundled: `voyage`, `cohere`, `bge`

### Embedder (shared with RAG)

- [ ] Interface: `Embedder` with `embed(texts, model) -> Embeddings`, `dims`, `max_tokens`
- [ ] Bundled: `voyage`, `openai`, `cohere`, `infinity` (self-hosted)

## Data Model (sketch)

- [ ] `providers(id, kind, enabled_default)` — system catalog
- [ ] `provider_credentials(id, org_id, provider, credentials_encrypted, label, last_health_at, healthy)`
- [ ] `models(id, provider, model_id, display_name, capabilities_json, price_input_per_1k_cents, price_output_per_1k_cents, price_cache_read_per_1k_cents, deprecated_at)`
- [ ] `model_aliases(id, org_id, alias, routing_policy_id)`
- [ ] `routing_policies(id, org_id, name, strategy, rules_json, created_at)`
- [ ] `rate_limit_rules(id, org_id, scope_json, dimension, period, limit, burst)`
- [ ] `prompt_cache_entries(hash, response_json, ttl, hits, created_at)` — Postgres-backed; Redis variant is ephemeral
- [ ] `guardrail_policies(id, org_id, name, bundle_json)`
- [ ] `guardrail_violations(id, org_id, request_id, guardrail, verdict, evidence_json, ts)`
- [ ] `request_traces(id, org_id, actor_json, route, model_requested, model_used, provider, status, latency_ms, ttft_ms, tokens_in, tokens_out, tokens_cache_read, tokens_cache_write, cost_cents, cache_hit, error, request_hash, ts)` — partitioned monthly
- [ ] `playground_sessions(id, org_id, user_id, snapshot_json, updated_at)`
- [ ] `model_evals(id, org_id, name, test_set_json)`
- [ ] `model_eval_runs(id, eval_id, target_model, results_json, summary_json, ran_at)`

## Public API (sketch)

- [ ] `POST /v1/chat/completions` (OpenAI)
- [ ] `POST /v1/messages` (Anthropic)
- [ ] `POST /v1/converse` and `/v1/converse-stream` (Bedrock)
- [ ] `POST /v1/embeddings`
- [ ] `POST /v1/rerank`
- [ ] `POST /v1/moderations`
- [ ] `POST /v1/messages/count_tokens`
- [ ] `GET /v1/models`
- [ ] `GET/POST /v1/gateway/providers/credentials`
- [ ] `GET/POST /v1/gateway/routing-policies`
- [ ] `GET/POST /v1/gateway/model-aliases`
- [ ] `GET/POST /v1/gateway/rate-limits`
- [ ] `GET/POST /v1/gateway/guardrail-policies`
- [ ] `GET /v1/gateway/traces` (search, filter)
- [ ] `POST /v1/gateway/traces/{id}/replay`
- [ ] `GET /v1/gateway/health`
- [ ] `GET/POST /v1/gateway/evals` / `POST /v1/gateway/evals/{id}/run`

## UI Surface

- [ ] Gateway → Overview (KPIs, top models, errors)
- [ ] Gateway → Providers (credentials, health, enable/disable)
- [ ] Gateway → Models (catalog, capabilities, pricing)
- [ ] Gateway → Routing (policies, aliases, drag-to-reorder priority)
- [ ] ~~Gateway → Rate Limits page~~ — **dropped**. Inbound limits are edited inline in **Admin → API Keys**; provider-side handling is automatic (Routing). Remove the dead `/gateway/rate-limits` nav item from `route.tsx`.
- [ ] Gateway → Guardrails (policy editor with live test)
- [ ] Gateway → Traces (table + detail + replay)
- [ ] Gateway → Playground
- [ ] Gateway → Evals
- [ ] Code snippets (cURL / Python / TS / Claude-Code config) per provider-compatible endpoint

### Access tiers

- [ ] Admin view (now): full Gateway console — create/manage provider creds, routing, limits, guardrails; mint API keys; see all teams' + all users' consumption and traces. Gateway is admin-only today (`isAdminActor` gate → 403 for non-admins).
- [ ] Member (individual) view — LATER: read-only. Sees only own consumption + own keys (read-only), no provider/routing/guardrail/limit management. Not built for v1.

## Dependencies on Other Modules

- [ ] Control Plane (hard)

## Acceptance Criteria

- [ ] Existing Claude Code CLI authenticates to gateway, makes requests, gets streamed responses, all audited
- [ ] LangChain `ChatOpenAI(base_url=...)` works against the gateway pointed at any backend provider
- [ ] An admin can mint a key with rate limits, routing policy, and guardrail bundle, and a developer's request is governed by all three
- [ ] Provider outage (simulated 5xx) triggers failover within 1 retry, observable in trace
- [ ] Budget breach returns 402 and emits webhook + audit + notification
- [ ] Replay of a historic trace reproduces the request, optionally on a different model

## Testing

- [ ] Unit tests per file in `server/api/src/ai_portal/catalog/`, `chat/`, `gateway/` (new), `guardrails/`
- [ ] Mock provider HTTP at the `httpx` layer with `respx`
- [ ] Run only touched-file tests during implementation
- [ ] Defer E2E to the final verification step
- [ ] E2E targets (added at the end): OpenAI-compat call routes correctly, Anthropic-compat streaming, failover on injected 503, rate-limit returns 429, guardrail blocks injected prompt, budget cutoff blocks call

### Frontend UI E2E coverage (GAP — currently ~90% untested)

Today `e2e/suite/gateway.spec.ts` only meaningfully tests the **Traces** page; the other 9 pages have no UI E2E. Two existing tests also bypass the UI (`page.evaluate(fetch(...))`) which violates the UI-only E2E rule. To implement later:

- [ ] Rewrite the chat-completion + 429 tests to drive the **Playground** UI instead of raw `fetch` (UI-only rule)
- [ ] Overview — KPIs + top-models/errors render
- [ ] Providers — list renders, add-credential form, health badge, enable/disable
- [ ] Models — catalog table renders with capabilities + pricing
- [ ] Routing — policy list, create/edit, drag-reorder priority (logic has a unit test; UI untested)
- [ ] Per-key rate limits — set RPM/TPM/concurrency when editing an API key; verify 429 enforced (no standalone Rate Limits page)
- [ ] Guardrails — policy editor + live test
- [ ] Playground — submit prompt, side-by-side compare, cost/latency shown
- [ ] Evals — create test set, run, results table
- [ ] Snippets — code snippets render per provider-compat endpoint
- [ ] Admin-gating — non-admin actor sees the `gateway-forbidden` 403 panel
