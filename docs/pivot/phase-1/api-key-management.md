# API Key Management

## 1. Purpose
Issue, scope, rotate, revoke gateway keys. Every LLM call traceable to one key, one human, one team.

## 2. Buyer pain (CISO)
- Devs paste raw OpenAI keys into Slack. No audit, no kill switch.
- Cannot answer "who called GPT-4 at 2am" or "kill that key now."
- Need SOC2/DORA-grade key hygiene before approving any GenAI spend.

## 3. Sub-features
- [must-have] (exists, table stakes) Hashed-at-rest keys, prefix-visible, shown-once. **Exists** (`portal_keys.py`, HMAC + pepper).
- [must-have] (audit = sale) Revoke + audit row on every use. **Partial** (revoked_at exists; audit log missing).
- [must-have] (SOC2 control evidence) Expiry (`expires_at`). **Missing.**
- [must-have] (blast-radius cap) Scope per provider/model allowlist. **Missing.**
- [must-have] (team chargeback need) Scope per team. **Missing** (only user+org today).
- [must-have] (zero-downtime hygiene) Rotation (issue new, grace window, auto-revoke old). **Missing.**
- [must-have] (FinOps gate) Per-key rate limit + monthly spend cap. **Missing.**
- [must-have] (kills Slack-key pain) Machine-identity tokens (JWT/OIDC for K8s workloads). **Missing** — bearer keys in Slack are the pain we sell against; workload identity closes it.
- [nice-to-have] (perimeter defense) IP allowlist / CIDR.
- [nice-to-have] (CI/CD owner) Service-account keys (no human owner).
- [skip] (phase 2 scope) mTLS client certs.
- [skip] (phase 2 scope) HSM-backed signing.

## 4. Actionable tasks
1. Add `teams` + `team_members` tables. Migration under `server/api/alembic/versions/`.
2. Extend `UserPortalApiKey` in `server/api/src/ai_portal/auth/model.py`: `expires_at`, `team_id` (nullable), `allowed_model_ids` (JSONB), `rate_limit_rpm`, `monthly_budget_usd`, `rotated_from_id`, `identity_kind` (`static|oidc`).
3. Extend `create_portal_api_key()` in `server/api/src/ai_portal/auth/strategies/portal_keys.py` with above kwargs.
4. Add `rotate_key()` in `server/api/src/ai_portal/auth/strategies/portal_keys.py`: clone scopes, return new raw, set grace `revoked_at = now + 24h` on old.
5. Add `verify_oidc_token()` sibling strategy next to `portal_keys.py`; map JWT `sub` to `UserPortalApiKey.identity_kind='oidc'` row.
6. Add `enforce_key_scope(user, key, model_id)` check; wire into `server/api/src/ai_portal/chat/router.py` before model call.
7. Add `api_key_audit` table (key_id, ts, ip, model_id, route, status, tokens, cost_usd). Write from `user_for_portal_api_key()`.
8. Frontend: extend keys page in `apps/frontend/src/components/admin/` — fields for scope, expiry, rotate button, OIDC issuer.
9. E2E: `apps/frontend/e2e/api-keys-scoping.spec.ts` — scoped key, blocked model, expect 403.

## 5. Competitive note
Portkey/LiteLLM ship per-model+budget keys day-one. Cloudflare AI Gateway has no scoping. Parity = scope+budget+rotation; differentiate on EU residency + workload identity + audit export.

## 6. Risks
- Design partner rejects bearer keys, demands SPIFFE/SPIRE — mitigate via OIDC trust + SPIFFE adapter on roadmap.
- Vendor schema drift (Anthropic ships workspace keys, OpenAI changes project-key shape) breaks our scope mapping.
- Scope check in hot path adds latency; cache key->scope in Redis.
- Rotation grace mis-set leaks revoked keys; default 24h, max 7d.
- JSONB allowlist drifts from catalog; FK or validate on write.

## 7. Done-when
CISO demo: scoped key (`gpt-4o-mini`, 50 USD/mo, 90d expiry), 403 on Opus, rotate, old key dies in 24h, K8s pod auths via OIDC, audit CSV export.
