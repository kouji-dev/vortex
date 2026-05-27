# Cost & Budget Control

## 1. Purpose
Hard-cap LLM spend per key/team/org. Real-time circuit-break before overage. Chargeback reports CFO can sign.

## 2. Buyer pain
- CFO: shadow AI spend, no per-BU attribution, surprise 5-figure invoices.
- CISO: rogue key drains budget in one night, no kill-switch.
- Existing `consumption_service` reports spend *after the fact*. Useless for control.

## 3. Sub-features
Pre-flight cost is **estimate**, not truth. Pattern: reserve on `max_tokens` claim → refund delta on stream close → nightly reconciliation fixes drift.

- [must-have] Budget object: scope (key|team|org), period (day|month), limit_usd, hard|soft. (core primitive)
- [must-have] Pre-flight reserve: deny with HTTP 402 + `X-Budget-Exceeded` when `max_tokens` projection breaches cap. (stops bleed before call)
- [must-have] Post-flight reconciliation: actual vs reserved on stream close; daily drift report. (estimate-only burns legit budget)
- [must-have] Live counter in Redis (or PG advisory + cached). Reset on period roll. (atomic concurrent decrement)
- [must-have] Alert thresholds (50/80/100%) → email + webhook. (CFO wants warning, not autopsy)
- [must-have] Chargeback CSV + signed PDF: org → team → user → model → tokens → USD. (CFO sign-off artifact)
- [must-have] Cost attribution tags (`team`, `cost_center`, `env`) propagated from API key metadata. (no tags = no chargeback)
- [nice-to-have] Soft-cap = downgrade model (sonnet → haiku) over 402. (graceful degrade)
- [nice-to-have] Forecast (linear extrapolation) on dashboard. (cheap, useful)
- [skip] ML anomaly detection. (thresholds cover 90%)
- [skip] Multi-currency. (USD only Phase 1)

## 4. Actionable tasks
1. Schema: `server/api/src/ai_portal/usage/budget_model.py` — `Budget`, `BudgetUsage`, `BudgetReservation`. Alembic migration.
2. Service: `server/api/src/ai_portal/usage/budget_service.py` — `reserve(scope, max_tokens_usd)`, `commit(actual_usd)`, `reconcile()`, `rollover()`.
3. Hook reserve in `chat/streaming/turn_setup.py`; commit + refund delta in `streaming/orchestrator.py` on stream close (incl. error paths).
4. 402 in `chat/router.py` + OpenAI-compat error in `/v1/chat/completions`.
5. Tag propagation: extend API key `metadata` jsonb; copy to `ThreadItem.data` in `streaming/item_writer.py`.
6. Admin UI: `apps/frontend/src/components/admin/BudgetsPage.tsx` — CRUD + threshold sliders, reuse `ConsumptionPage.tsx` patterns.
7. Chargeback export: extend `api/admin/consumption.py` with `/export.csv` and `/export.pdf`.
8. Alerts: `usage/alert_dispatcher.py` — email + webhook, idempotent per threshold/period.
9. Reconciliation cron: nightly job, drift report to admin dashboard.
10. E2E: `apps/frontend/e2e/budgets.spec.ts` — create budget, exceed via mocked stream, assert 402 + UI banner.

## 5. Competitive note
Portkey/LiteLLM offer budgets but weak chargeback. Cloudflare AI Gateway has no per-team attribution. Win = bank-grade signed PDF + soft-cap downgrade + honest reconciliation.

## 6. Risks
- Race on concurrent requests near cap → Redis INCR or PG `SELECT FOR UPDATE`.
- Estimate drift on streams → reserve high, refund on commit, reconcile nightly.
- **Over-reservation blocks legit calls before budget actually hit** → tune reserve multiplier; expose `effective_remaining` vs `committed_remaining` in UI.
- **Provider pricing changes mid-month break projection** → snapshot pricing on each `ThreadItem`; reconciliation uses snapshot, not live rate card.
- **Shared portal-key across services = no clean attribution** → enforce one-key-per-service in onboarding; refuse to issue shared keys without `cost_center` tag.

## 7. Done-when
Demo: set $10/day org budget, stream until 402, show alert email + chargeback CSV split by team + nightly drift report.
