# Prompt Caching

## 1. Purpose
Cut LLM bill + p50 latency by caching prompts at the gateway and passing through provider-native caches with full visibility.

## 2. Buyer pain (CFO + Platform Eng)
- CFO: same RAG context re-billed 1000x/day. Provider caches help but invisible at portfolio level.
- Platform Eng: no per-team hit-rate, no TTL knob, no way to opt out a key that breaks under cached responses.

## 3. Sub-features
- [must-have] Provider-native cache passthrough (table-stakes parity). **Exists** Anthropic (`anthropic_native.py:137,244`) + Gemini (`gemini_native.py:277`). Extend OpenAI (`prompt_cache_key`).
- [must-have] Cache key namespaces by org_id + portal-key-id + tools digest + provider + model (cross-tenant hit = GDPR P0 breach; tenant isolation non-negotiable). **Was tagged nice-to-have — wrong.**
- [must-have] Cache token metrics per key/team/model (CFO rollup demand). **Partial** — fields recorded (`cached_input_tokens`, `cache_creation_input_tokens`); no dashboard.
- [must-have] Exact-match gateway cache, sha256 canonical request → response, Redis, TTL configurable (core win vs Portkey).
- [must-have] Per-key opt-in `cache_mode: off | passthrough | exact` (some keys break under replay).
- [must-have] TTL config: org default + per-key override; bypass header `x-cache: no-store` (24h cap; masks model upgrades).
- [must-have] Cost-savings counter in USD on consumption page (CFO demo hook).
- [nice-to-have] Stream replay from exact-match cache, re-emit SSE chunks (latency polish, not core).
- [skip] Semantic cache, embedding + ANN (false hits in banking = compliance incident; Portkey headline but liability).
- [skip] Distributed multi-region cache replication (no buyer asking).

## 4. Actionable tasks
1. Add `cache_mode`, `cache_ttl_seconds` to `UserPortalApiKey` (`auth/model.py`) + migration.
2. New `chat/cache/` module: `key_builder.py` (canonical sha256, MUST prefix `{org_id}:{portal_key_id}:`), `redis_store.py`.
3. Hook in `streaming/orchestrator.py` before provider call: lookup → replay SSE on hit; miss → tee stream into store.
4. Extend `cost_calculator.py` + `llm_pricing.py` for `usd_saved` from `cached_input_tokens`.
5. `cache_events` table (org_id, key_id, model_id, ts, hit_kind, tokens_saved, usd_saved).
6. Extend `consumption_service.py` aggregations + Cache panel in `ConsumptionPage.tsx`.
7. E2E `prompt-caching.spec.ts`: identical request twice, second is hit, KPI updates. Cross-tenant test MUST prove no hit.

## 5. Competitive note
Portkey: exact + semantic + per-key TTL. LiteLLM: Redis exact. Cloudflare AI Gateway: exact only. Parity bar = exact + passthrough + metrics. Semantic = Portkey headline but EU-banking liability.

## 6. Risks
- Cross-tenant cache hit = GDPR P0 incident if namespace slips. Mandatory unit + E2E test on key construction.
- Hash collision / sloppy canonicalization: missing field (tools, system, params) → wrong-tenant or wrong-tool replay. Version + schema-pin the canonical form.
- Prompt-injection probe: attacker crafts inputs to fish cached completions from other tenants. Namespacing per org_id + portal-key-id blocks; log negative-result probes.
- Provider-native cache TTL changes silently invalidate hit-rate claims on dashboard. Pin provider cache assumptions; alert on drift.
- Tool-calling replays run stale side effects; exclude `tool_choice != none` from exact cache.
- TTL too long masks model upgrades; cap 24h.
- SSE replay drifts if `item_kinds.py` evolves; version cache entries.

## 7. Done-when
CFO demo: bank-scale RAG, dashboard >40% hit-rate, USD saved ticks, ops toggles key `cache_mode=off`, hits drop to zero live. Cross-tenant E2E proves zero leakage.
