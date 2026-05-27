# Multi-Provider Routing + Failover

## 1. Purpose
One gateway. Many LLMs. Route by policy. Failover on error. No vendor lock.

## 2. Buyer pain (CISO/RSSI)
- One vendor down = AI products down. No SLA leverage.
- Sovereignty: GenAI in EU jurisdiction, no US-only path. DORA + EU AI Act.
- No central audit of which model handled which prompt.

## 3. Sub-features
- [must-have] Mistral on-prem provider (sovereign EU story; vLLM/TGI HTTP)
- [must-have] Bedrock-Anthropic provider (failover twin of native Anthropic)
- [must-have] Policy engine: primary -> fallback chain per route, per tenant (core value prop)
- [must-have] Schema-family failover only (silent behavior drift breaks customer apps)
- [must-have] Retry policy: backoff + jitter; classify 429/5xx/timeout/ctx-overflow (table stakes)
- [must-have] Circuit breaker per provider+model; health probe (stops cascade)
- [must-have] Routing decision log -> audit table (DORA evidence)
- [nice-to-have] Cost-aware routing (cheapest meeting SLO; not P0)
- [nice-to-have] Shadow traffic (mirror N% to candidate; ops-only win)
- [nice-to-have] Region pinning (EU-only routes; subset of policy engine)
- [skip] Custom DSL for routing (YAML enough Phase 1)
- [skip] Cross-provider semantic cache (Phase 2 scope)

## 4. Provider Semantics Drift
Providers diverge on: tool-call schemas (OpenAI `tool_calls[]` vs Anthropic `input_json_delta` vs Gemini `functionCall`), `stop_reason` values (`end_turn`/`stop`/`STOP`/`MAX_TOKENS`/`tool_use`), JSON-mode contracts (strict schema vs best-effort vs `responseSchema`), streaming chunk shapes. Equivalence policy: failover targets must share a `schema_family` tag (e.g. `anthropic-tools-v1`, `openai-tools-v1`). Cross-family routes require explicit opt-in + adapter; default = block. Snapshot tests pin event mapping per family.

## 5. Tasks (build order)
1. Add `catalog/providers/mistral_onprem.py` (OpenAI-compatible base URL).
2. Add `catalog/providers/bedrock_anthropic.py` (reuse `anthropic_native.py` mapping).
3. Extend `LlmProviderFactory.create` -> dispatch `mistral-*`, `bedrock/anthropic.*`.
4. `catalog/providers/failover.py`: `FailoverChatProvider` wraps primary + ordered fallbacks; enforces `schema_family` match.
5. `catalog/providers/policy.py`: route table from `settings` (tenant -> model -> chain).
6. Circuit breaker per (provider, model); Redis-backed if `REDIS_URL` set.
7. Audit: `routing_decision` table; `/admin/routing` read API.
8. Wire `chat/streaming/orchestrator.py` through policy layer.
9. E2E `routing-failover.spec.ts`: mock primary 503, assert fallback + audit row.
10. Sync `lib/chat-types.ts` on new event fields.

## 6. Competitive note
Portkey/LiteLLM: SaaS-first, US data plane. Cloudflare AI Gateway: no on-prem. We win on EU-sovereign Mistral + self-host + DORA audit.

## 7. Risks
- Anthropic/OpenAI/Gemini ship breaking schema changes monthly; pin SDK versions, run weekly contract tests.
- Mid-stream failover impossible Phase 1; pre-first-token only. Document the limit.
- Mistral self-host latency much higher than SaaS Mistral; sovereignty vs perf tradeoff; expose SLO probes.
- Bedrock-Anthropic event parity drift -> snapshot tests vs native.
- Cross-family failover silently changes tool-call shape -> blocked by default; explicit opt-in required.

## 8. Done-when
Kill primary Anthropic, prompt continues on Bedrock; admin shows row reason `primary_5xx`. Toggle tenant to Mistral on-prem; same prompt routes sovereign.
