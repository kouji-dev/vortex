# Rate Limiting

## 1. Purpose
Hard-cap request rate and token throughput per key, team, and model. Independent of cost budgets. Protect upstreams and bank wallets from runaway scripts.

## 2. Buyer pain (CISO + Platform Eng)
- One looping notebook drains the org's OpenAI quota in 10 min; whole bank is throttled mid-trade.
- Platform Eng cannot rate-limit per team without a custom proxy. Today there is no QPS shield.
- CISO wants enforceable ceilings before signing the GenAI policy; soft cost cap is not enough.

## 3. Sub-features
- [must-have] Per-key requests-per-second (token bucket, Redis). (core QPS shield)
- [must-have] Per-key tokens-per-minute, pre-reserved on `max_tokens`, refunded on close. (parallel-stream bypass kill)
- [must-have] Per-key concurrent stream cap. (1 key, 100 streams overruns provider quota even at low QPS)
- [must-have] Per-team aggregate RPS + TPM. (team budget enforcement)
- [must-have] Per-model global ceiling. (protect shared upstream quota)
- [must-have] 429 + `Retry-After` + structured error code. (client backoff contract)
- [must-have] Bypass list for admin/ops keys. (avoid locking out operators)
- [must-have] Admin UI: set/view limits, live usage. (CISO demo surface)
- [nice-to-have] Burst factor (2x for 10s). (smooths legit spikes)
- [nice-to-have] Per-route limits (chat vs embeddings vs files). (route-shape differs)
- [skip] Adaptive/AI-driven limits. (phase 2, no buyer ask)
- [skip] Geo-based limits. (phase 2, no buyer ask)

## 4. Actionable tasks
1. Redis client module `server/api/src/ai_portal/core/redis.py` (single async client, URL from `core/config.py`).
2. Service `server/api/src/ai_portal/usage/rate_limit_service.py` — token-bucket Lua, `check(scope_key, cost) -> Allow|Deny(retry_after)`. Scopes: `key:{id}`, `team:{id}`, `model:{id}`. Add `reserve_tokens(scope, max_tokens)` + `refund_tokens(scope, max_tokens - actual)`. Add `acquire_stream_slot` / `release_stream_slot` (Redis INCR with TTL fence).
3. Extend `UserPortalApiKey` (`auth/model.py`): `rate_limit_rps`, `rate_limit_tpm`, `max_concurrent_streams`. Alembic migration.
4. `Team.rate_limit_rps`, `Team.rate_limit_tpm`, `Team.max_concurrent_streams`.
5. `models.rate_limit_rps`, `models.rate_limit_tpm` on catalog row.
6. In `chat/router.py`: pre-stream → `check_request` + `reserve_tokens(max_tokens)` + `acquire_stream_slot`; post-stream (finally) → `refund_tokens(delta)` + `release_stream_slot`.
7. 429 mapping in `chat/streaming/error_handler.py` — emit `rate_limited` SSE event.
8. Admin endpoint `api/admin/limits.py` — GET/PUT per-key, per-team, per-model.
9. Frontend limits panel in `apps/frontend/src/components/admin/` — fields on key + team forms.
10. E2E `apps/frontend/e2e/rate-limiting.spec.ts` — 2 RPS, 5 calls → 3x 429; parallel-stream test verifies TPM reservation blocks bypass.

## 5. Competitive note
Portkey + LiteLLM ship RPS+TPM per key. Cloudflare AI Gateway has crude per-gateway limits, no team scope. Parity bar = per-key+team+model bucket; EU-resident Redis is the wedge.

## 6. Risks
- Redis HA outage: fail-open = silent limit bypass; fail-closed = full outage, revenue hit. Default fail-closed for paid tiers, fail-open for free, both alarmed. Config per-deployment.
- Provider's own rate limit fires below our cap → customer sees 429 but our UI shows headroom. Surface upstream 429 distinctly (`upstream_rate_limited` error code) to avoid double-limit confusion.
- TPM pre-reservation over-reserves when callers set huge `max_tokens`; refund closes gap but transient over-deny possible. Document and expose effective reservation in admin UI.
- Clock skew across replicas; use Redis time in Lua, not wall clock.
- Per-model global ceiling default too low blocks legit usage; ship generous defaults.

## 7. Done-when
Platform Eng demo: set key to 2 RPS / 10k TPM / 3 streams, run a loop + 5 parallel streams, see 429 with `Retry-After: 1`, watch counters live in admin UI, confirm other keys unaffected.
