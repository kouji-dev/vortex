# Plan — Vortex governance + pricing (backend)

## Idea
Budget first. Rate limit second. Billing only on managed.

## Rules (from you)
- Budget = team level. Enforce both managed + self-host.
- Rate limit rides on budget. Check budget first, then rpm/tpm.
- Seats capped per plan. Free + Pro capped, Enterprise unlimited.

## Two planes
- Meter + budget + rate limit → everywhere (managed + self-host).
- Billing (Stripe) → managed only. Gate: `DEPLOYMENT_MODE` = managed | self_hosted.

## Request order
auth → budget (team $, 402) → rate limit (rpm/tpm/concurrency, 429) → proxy → commit spend + usage.
Budget = main gate. Rate limit = backstop.

## Seats / services (enforce on member + service create)
| Plan | Members/org | Service/member | Budget | Rate limit |
|---|---|---|---|---|
| Free | 2 | 1 | team cap, hard | low (~20 rpm) |
| Pro | 10 * | 3 * | team cap | higher (~600 rpm) |
| Enterprise | ∞ | ∞ | team cap, custom | custom |

`*` Pro numbers = proposed. Say the word to change.

## Pricing table
| Plan | Price | Bills on | Deploy |
|---|---|---|---|
| Free | $0 | nothing | managed |
| Pro | $/seat + usage overage | seats + tokens | managed |
| Enterprise | contract | seats + usage (graduated + commit) | managed, or self-host flat |

## Enterprise priced on
Seats + usage volume (tokens/$). **Graduated**: unit price drops as volume grows. Committed base + overage. Negotiated per contract.

## The fee (managed-key markup)
- Fee = % markup on spend.
- Applies ONLY to spend on **Vortex-managed keys**.
- Needs the managed-keys feature → now in scope (step 6).

## BYOK (works without managed keys)
- Customer's own provider keys. Provider bills customer direct. Vortex not reselling.
- **No token markup.**
- Still pay: seats + platform fee (Pro flat / Enterprise contract).
- Usage still tracked + budgeted. Just not marked up.

## Managed keys (new feature — unlocks the fee)
- **Vortex owns the provider accounts.** Org brings no key.
- Org buys **credits**. Request → Vortex calls provider with its own key, pays provider, deducts org credits **+ markup %**.
- Mode per org: **BYOK | managed | hybrid**.
- Resolver: org has no BYOK cred for the model → use managed pool.
- Credit wallet: balance + Stripe top-up + deduct on spend; **402 when credits = 0**.
- Managed pool = platform-scoped provider creds (reuse encrypted-cred mechanism, owned by platform not org).
- Managed only (Stripe = managed). Self-host stays BYOK.
- Bonus: managed pool later enables failover/routing (still deferred).

## Build steps
1. **Budget → team aggregate.** Today it's member-level (`budget.service.ts`). Make team the pool. Both deploys.
2. **Seat/service caps.** Enforce on member + service-account create against plan entitlements. Block over cap.
3. **Rate limit engine.** GCRA Lua (rpm/tpm/concurrency), runs after budget. Ceilings from entitlements. Both deploys.
4. **Entitlement + pricing tables.** See Data.
5. **Billing (managed only).** Stripe metered: seats + usage overage, graduated from `pricing_tiers`. `DEPLOYMENT_MODE=managed` gate.
6. **Managed keys (managed only).** Platform-scoped provider pool + org credit wallet + BYOK|managed|hybrid mode + resolver fallback + markup metering + credit-exhaust 402.
7. **Pricing read APIs.** `GET /billing/plans` (public pricing catalog from `plan_entitlements`+`pricing_tiers`) + `GET /billing/subscription` (current org plan/seats/usage).
8. **Frontend** — see below.

## Frontend (kouji-ui, per CLAUDE rules)
- **Landing pricing (public).** New `apps/web/src/app/features/pricing/pricing.ts`. Register in `app.routes.ts` **outside** the authGuard shell (top-level, like `login`). 3-tier table: Free / Pro / Enterprise — seats, service/member, budget, rate limit, price. Use `KjCard*`, `KjBadge`, `KjButton`, `KjTag`. Data from `GET /billing/plans`.
- **Settings plan card.** `features/settings/settings.ts` org-profile panel already has a `Plan` stat (~line 77). Add a current-plan `KjCard` (tier + seats used/limit + budget) reading `GET /billing/subscription`. Replace `settings.data.ts` mock (`plan: 'Enterprise'`) with the real service.
- **Billing route.** `app.routes.ts:67` `billing` currently a `Stub`. Replace with plan view: current plan + same pricing table + upgrade CTA (managed only).
- Net-new `Plan`/`Subscription` interface (tier, price, seats, entitlements) + data service wired to the read APIs.
- **Design gap:** no design exists for landing/pricing. Align to kouji-ui + preesm patterns. If a pricing-specific kouji-ui component is missing → fix/release in `./projects/kouji-ui` (rule 3), else flag for a design.

## Data (new / changed)
- `plan_entitlements`: seatsPerOrg, servicePerMember, teamBudgetMicro, rpm, tpm, concurrency, flags.
- `pricing_tiers`: (plan|contract, meter, upToQty, unitPriceMicro). Graduated. Billing only.
- `contracts`: per-org enterprise overrides (base, term, schedule, seatCommit).
- `usage_rollups`: org/period × meter (requests, tokens, cost, seats, services). Reuse `reconcileMonth`.
- `credit_wallets`: org balance (micro), top-ups, deductions. Managed only.
- `providerCredentials`: add platform-scoped (managed pool) rows; org `keyMode` = byok|managed|hybrid + `markupBps`.
- env: `DEPLOYMENT_MODE`, `RATE_LIMIT_FAIL_OPEN`.
- `budget.service.ts`: member-level → team aggregate.

## Reuse
`budget.service` (reconcile, spendKey, redis), `usage_records`, `cost.ts` pricing, memberships human/tech split, `billing.service` (Stripe), `audit.service`, `withOrg`/RLS.

## E2E (must pass, no skip)
- Free: 3rd member → blocked. 2nd service on a member → blocked.
- Budget: team cap hit → 402. Managed + self-host.
- Rate limit: over rpm → 429; big-token req → tpm 429; fires after budget.
- Managed: usage crosses tier → billed at stepped unit price.
- Self-host: no Stripe calls, but track + budget + rate limit all work.
- BYOK: spend tracked + budgeted, NOT marked up.
- Managed keys: org w/ no BYOK cred → served from managed pool; spend deducts credits + markup; credits = 0 → 402.
- FE landing: `/pricing` public (no auth) renders 3 tiers from `GET /billing/plans`.
- FE settings: current-plan card shows real tier + seats used/limit from `GET /billing/subscription`.
- FE billing route: plan view + pricing table + upgrade CTA (managed).

## Verify
`pnpm db generate && migrate` + `build` clean. Stack up (pg+redis+api:8080+mock-provider). Seed plans/entitlements/tiers. `pnpm playwright test e2e/gateway.spec.ts` pass. Smoke: `DEPLOYMENT_MODE=self_hosted` → usage tracked, budgets enforced, no billing wired.

## Out of scope
Failover, smart routing, caching, async worker (deferred — failover rides on the new managed pool, do later). Self-host commercial licensing = flat contract, out-of-band.
