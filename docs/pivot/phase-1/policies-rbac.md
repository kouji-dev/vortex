# Policies & RBAC

## 1. Purpose
Central policy engine. Decides per request: which model, which region, which tools, which context size — for which key/team/user.

## 2. Buyer pain (CISO)
- Cannot prove "no EU bank data left EU region" without policy enforced at gateway.
- Dev teams self-serve any model, any tool, any prompt size — no guardrail before invoice.
- Auditor asks "who can call US-hosted Claude?" — today, nobody knows.

## 3. Sub-features
- [must-have] Allowed-models per key/team (core wedge). Reuse `rbac_policy.model_allowlist`.
- [must-have] Allowed-regions, EU-only flag (residency proof). **Missing** — add `region_allowlist`.
- [must-have] Max-context-tokens per policy (cost gate). **Missing.**
- [must-have] Tool-use allow/deny per policy (blast-radius limit). Partial.
- [must-have] Hierarchical resolve org→team→key, most-specific wins (real-world org shape). Today only org-level.
- [must-have] Deny-by-default mode (regulated tenants demand it). Wire to UI.
- [must-have] Policy decision logged in audit-log — every allow/block with rule that fired (CISO needs forensics).
- [nice-to-have] PII redaction toggle (downstream of policy hook).
- [nice-to-have] Time-of-day window (low-priority compliance ask).
- [skip] Full policy DSL / Rego / Cedar (overkill; JSONB ships weeks vs DSL quarters).
- [skip] ABAC beyond role+team (no buyer asking).

## 4. Migration path
- Phase 1 = JSONB flat fields on `rbac_policy`. Cheap, fast, indexable.
- Phase 2 = adopt Cedar (AWS) or OPA/Rego if customers demand DSL.
- Rationale = ship speed now; refactor cost bounded — fields map to DSL predicates 1:1.

## 5. Actionable tasks
1. Migration: add `region_allowlist JSONB`, `max_context_tokens INT`, `tool_allowlist JSONB`. New `rbac_policy_scope` (policy_id, scope_type ENUM[org,team,key], scope_id).
2. Extend `evaluate()` in `rbac/evaluator.py`: load (org, team, key), merge most-specific-wins, check region + max_context + tool_allowlist. Emit decision record.
3. Pre-call gate in `chat/streaming/turn_gate.py` — block before provider call.
4. Provider region tag: extend `models.region`; populate via `scripts/sync_*_models.py`.
5. Audit-log writer: append `{policy_id, rule, decision, subject}` on every gate hit.
6. API: extend `auth/routes_rbac.py` with policy CRUD + scope attach.
7. Frontend: policy editor under `admin/` — list, create, attach.
8. E2E: `rbac-policies.spec.ts` — EU-only key calls US model → 403; oversize prompt → 413; audit row asserted.

## 6. Competitive note
Portkey: guardrails + virtual keys, no region. LiteLLM: budgets, weak region. Cloudflare AI Gateway: no policy engine. EU-region is our wedge.

## 7. Risks
- JSONB policy grows hairy past 6 months → forced DSL migration under deadline.
- Hierarchical resolution order disputes (org vs team vs user vs key) burn support tickets — document precedence early, surface in UI.
- Deny-by-default breaks dev velocity if not staged — gate behind per-org flag, dry-run mode first.
- Hot-path DB hops — cache resolved policy in Redis, TTL 60s, invalidate on write.
- Region tag drift from provider reality — pin via signed catalog.

## 8. Done-when
CISO demo: deny-default tenant, EU-only on team-A key — Claude EU passes, US Opus 403s, 200k prompt 413s, audit row shows policy_id + rule.
