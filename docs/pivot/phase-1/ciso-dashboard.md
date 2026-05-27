# CISO Dashboard

## 1. Purpose
CISO/RSSI single-pane. First screen post-login. Proves control + spend + AI Act posture in <10s.

## 2. Buyer pain
- Shadow AI, no audit trail.
- Can't answer per-team LLM spend.
- AI Act Art. 15/26 + DORA: monitoring, logging, oversight.

## 3. Sub-features
- KPI row: spend MTD, tokens, top model, blocked, active keys, violations 24h [must-have] (10-sec proof)
- Spend-by-team stacked bar 7/30/90d [must-have] (finance) — reuses `consumption_service.trend`
- Top-10 users table [must-have] (shadow-AI) — reuses `consumption_service.threads`
- Model-mix donut [must-have] (vendor risk)
- Blocked-requests feed: PII, injection, policy, quota [must-have] (security primitive)
- Policy-violations widget → audit search [must-have] (AI Act evidence)
- Audit search bar: user, model, date, redaction [must-have] (DORA) — extend `AuditLogPanel`
- Key-health strip: expiring, unrotated >90d, unused 30d [must-have] (hygiene)
- Materialized views / Redis cache for KPIs [must-have] (live aggregation over audit table = dies at scale)
- Degrade-gracefully fallback: last snapshot + staleness badge [must-have] (dashboard IS the demo; no blank screen on stage)
- Screenshot/PNG export [must-have] (board reports — inevitable PM ask)
- EU AI Act risk indicators [nice-to-have] (theater risk)
- CSV/PDF export [nice-to-have] (finance follow-up)
- Real-time alert ticker (WebSocket) [nice-to-have] (cool, not critical)
- Predictive spend forecast [skip] (no data)
- Per-prompt sentiment [skip] (privacy minefield)

## 4. Actionable tasks
1. New `CisoDashboardPage.tsx` — grid, KPI row, 4 slots.
2. Extract widgets from `ConsumptionPage.tsx` → `admin/widgets/`.
3. New `api/admin/security.py`: blocked/violations/key-health.
4. New `usage/security_service.py` over audit + consumption. No new schema.
5. `team_id` group-by in `consumption_service.trend`.
6. Audit search → `AuditLogPanel` via query string.
7. Default landing for `owner`/`admin` in `__root.tsx`.
8. E2E `ciso-dashboard.spec.ts`: KPIs, widgets, deep-link.

## 5. Competitive note
Portkey/LiteLLM = dev. Cloudflare AI Gateway = ops. None lead CISO + AI Act. Framing IS the wedge.

## 6. Risks
- Reskinned-admin smell — security primitives day one or demo flat.
- Spend-by-team needs team tagging; absent → top-users carries demo.
- AI Act indicators = theater unless tied to real log query.
- Widgets stream/lazy-load. TTI <1s.
- High-cardinality filters (user × model × day) blow query plans — pre-aggregate.
- CISO demands alerts (Slack/email/PagerDuty) — Phase 1 or punt? Default punt, stub UI.
- Board-report export = PM ask. Design PNG/PDF path day one.

## 7. Done-when
CISO login → 6 KPIs + 4 widgets, real data → click blocked → filtered audit. SG-demo-able, no storyboard.
