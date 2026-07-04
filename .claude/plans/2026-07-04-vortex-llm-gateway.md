# Vortex — Enterprise LLM Gateway (fresh start)

## Context

The previous project (a sprawling 5-module "AI Portal" suite) was hard-reset to an
empty `main`. Old code is preserved on the `pivot` branch (remote `b475d5d`). We are
restarting **small and focused**: a single, sharp product — an **enterprise LLM
gateway** — built with startup logic (ship the moat, skip the sprawl).

**Guiding principle:** **enterprise-first** (teams + governance). Our SaaS is **multi-tenant,
hosting enterprise client orgs** — not a solo-dev self-serve play.

**Deployment (foundational):** two shapes on **one codebase** — **dedicated / on-prem per client**
(single-tenant) and **our multi-tenant SaaS** (many client orgs). **Multi-tenancy + strict
`org_id` isolation are built in from day one** (they can't be retrofitted safely).

**Why this shape:** research into LLM Gateway (theopenco/llmgateway), its DevPass
sub-product, and the enterprise gateway landscape (Portkey, LiteLLM, TrueFoundry,
Helicone, Cloudflare/Kong AI Gateway) shows the proxy itself is commodity. The **actual
moat for enterprises is the governance layer**: cost caps, RBAC, audit. The non-negotiables
without which an enterprise gateway "makes no sense": (1) cost governance / hard spend caps,
(2) observability + audit, (3) RBAC + org hierarchy, (4) SSO (later). We ship 1–3 in v1.

We are **inspired by** LLM Gateway but building a **unique product** — reference their
routing ideas, write our own code. Project is **private, under active development**, so
their AGPLv3 licensing is not a blocker now.

## Decisions (locked)

| Area | Choice |
|---|---|
| Frontend | **Angular 22 SSR** + **kouji-ui** (user's own component lib) |
| Backend | **Hono** (TypeScript) — lightweight, speed-first; native Web-Streams SSE ideal for the proxy hot path |
| Runtime / speedup | Node via `@hono/node-server`, **Bun-ready**. (Fastify was the alternative; Hono chosen for the streaming-proxy fit + llmgateway lineage.) |
| ORM / DB | **Drizzle ORM** + **Postgres** |
| Cache / counters / queue | **Redis** |
| Validation | **Zod** everywhere — env config (boot-time, fail fast), inbound API request/response schemas (Hono `@hono/zod-validator`), the format-adapter schemas (Chat / Messages / Responses), and shared DTOs; `drizzle-zod` to derive validators from the DB schema. |
| Repo | **pnpm monorepo**: `apps/api` (Hono), `apps/web` (Angular tenant console), **`apps/platform`** (Angular super-admin console — **separate app** for the cross-tenant security boundary; `multi` mode only), `packages/db`, `packages/core`, `packages/shared`, `packages/sdk`. *(Monorepo `apps/` = workspace tooling — unrelated to the domain entity **App**.)* |
| v1 scope | **Core gateway + governance** (detailed below) |
| Money | integer **micro-USD** (no float drift) |
| Virtual keys | hashed at rest (SHA-256), prefix `vtx_` |
| Tenancy | **Multi-tenant from day one.** A deployment hosts **one org** (client on-prem/dedicated) or **many orgs** (our SaaS) — same codebase, `TENANCY_MODE = single \| multi`. **Every row `org_id`-scoped, strict isolation.** End-users belong to **one org, no org switcher**. A **platform super-admin** layer manages tenant orgs in SaaS mode. |
| Naming | Deployable services / internal tools / agents are **Apps**. |
| API surface | **OpenAI Chat (`/v1/chat/completions`) + Anthropic Messages (`/v1/messages`) + OpenAI Responses (`/v1/responses`) + `/v1/embeddings` + `/v1/models`**, with **cross-format transform** (Anthropic ⇄ OpenAI). No proprietary SDK — change the base URL. Covers Claude Code (Messages) + Codex (Responses). Images/audio/video later. |
| Config | **Deployment-specific config via env vars / env files** (one image → SaaS / enterprise / air-gapped). Enabled providers + base URLs, models, flags, infra, encryption keys — all env-driven. See §0b. |
| Billing | **Stripe** (SaaS `multi` only) — org = Customer + Subscription to a plan; **Stripe-hosted Checkout + Portal (no card data on us)**; webhooks → org lifecycle (suspend on unpaid). On-prem = contract/license. See §E. |
| Org roles | **owner / admin / member** only (3 roles for now). |
| Teams | A member belongs to **exactly one team**; team is the usage/budget layer. |
| Budgets v1 | **Monthly, per-member.** Effective ceiling = team's **default-per-member** budget, or a **per-member override**; applies across **all apps**. **Apps & keys are attribution only**, not budget scopes. Reset on the 1st. |

Deferred (later): **Chat UI** (backend ships in v1), **platform phase-2** (support view-as/
impersonation, global provider mgmt console, platform alerts, feature flags),
**gateway images/audio/video endpoints**, **model aliases**, **team-scoped provider creds**,
SSO/SAML/SCIM, PII guardrails, prompt caching, weighted smart-routing, white-label, self-host/Helm,
compliance certs, daily/custom budget periods.

## v1 scope — detailed

### 0. Multi-tenancy, deployment & isolation (foundational — day one)
- **Two deployment shapes, one codebase** via `TENANCY_MODE`:
  - `single` — a client's **dedicated / on-prem** install: one seeded org, no platform layer, no signup.
  - `multi` — **our SaaS**: many client orgs, org **provisioning / signup**, a **platform super-admin**.
- **Strict tenant isolation (defense-in-depth):** every table carries `org_id`; **app-level
  org-scoped query layer + Postgres Row-Level Security** (per-table policies keyed to a session
  `app.current_org`, set per request) — a buggy query still can't cross tenants. Every Redis key &
  cache entry org-scoped (`spend:{org}:…`); provider-cred encryption uses **per-org** key derivation.
- **Platform layer (SaaS only, above orgs):** a **vendor super-admin console (v1)** — tenant-orgs
  list, provision / suspend / plan, cross-tenant health & usage; a **separate identity** from org
  members; **end-users never switch orgs**. (Per-org **billing / subscriptions** phased.)
- **Org lifecycle:** provision (signup or vendor-created) → active → suspended → deleted (with
  tenant data purge). First user of a new org = its **owner**.

### 0b. Configuration & deployment (env-driven — per SaaS / enterprise install)
- **Everything deployment-specific is configurable via env vars / env files** (`.env` or mounted
  env / secrets) — **one image, no code changes** serves our **SaaS**, a client **enterprise/on-prem**
  install, or an **air-gapped** one.
- **Provider/model availability is layered — each narrows the previous:**
  1. **Code registry (§A):** the **full catalog** of providers + models our code knows (definitions,
     default URLs, transforms) — the `ProviderRegistry` in code (this is what "our SDK manages all
     providers" means — not a client SDK).
  2. **Deployment env:** **activates / deactivates** which providers + models *this install* offers,
     and overrides base URLs / endpoints (SaaS = broad; enterprise = restricted / self-hosted).
  3. **Org admin (tenant panel):** from the **env-allowed** set, the org **further enables / disables**
     providers + models for itself (a distinct layer — not the same as the env list).
  → **Effective availability = code ∩ env ∩ org**; per-org **BYOK creds** still override base URL at
  runtime (**BYOK > env > default**).
- **Env-configurable (examples):**
  - `TENANCY_MODE` (single | multi).
  - **Enabled providers** + per-provider **base URL / endpoints** (point OpenAI → **Azure**, add a
    **self-hosted OpenAI-compatible** endpoint, route via a **private proxy**) + auth style.
  - Available **models / catalog** + default routing policy; **feature flags** (which hubs/features on).
  - Infra: Postgres / Redis URLs, **encryption key(s)**, base domains; auth/SSO + branding (later).
  - **Stripe** (SaaS only): `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, portal/checkout config.
- **Enterprise/on-prem specifics via env:** restricted provider list, private/self-hosted model
  endpoints, air-gapped (no public providers), customer-held encryption keys.
- Since provider/model **definitions live in code**, **env only carries simple activation toggles +
  URL / secret overrides** — **flat env is enough** (no structured config file needed).

### A. Gateway proxy (the plumbing)
- **Multi-format, drop-in surface** (no proprietary SDK — clients **change the base URL** of their
  existing OpenAI / Anthropic SDK or tool):
  - `POST /v1/chat/completions` (OpenAI Chat, stream + non-stream) — Cursor / Cline / Aider / OpenAI SDK.
  - `POST /v1/messages` (**Anthropic Messages**, stream) — **Claude Code**.
  - `POST /v1/responses` (**OpenAI Responses**) — **Codex CLI**.
  - `POST /v1/embeddings` (RAG / search); `GET /v1/models`. OpenAI-shaped errors.
  - Coding agents connect by env only: Claude Code `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`
    (+ `ANTHROPIC_MODEL`); Codex `openai_base_url`.
- **Hub-and-spoke (inspired by llmgateway):** **OpenAI Chat is the canonical internal format.**
  `/v1/messages` and `/v1/responses` are **thin inbound adapters** — validate native schema (**Zod**) →
  transcode to canonical → re-enter the **single core handler** → transcode response/stream back. Only
  **OpenAI↔provider** transforms exist (not pairwise), so adding a format (incl. Responses) is a
  **cheap spoke** → **all three formats ship in v1**. Any client format can drive **any catalog model**
  (Claude Code → a GPT/Gemini model).
- **Data-driven provider registry ("reroute by model"):** each provider = `{ base_url, endpoint
  path(s) per capability, streaming variant, auth style, body transform }`. Flow: **model → provider
  (registry) → build upstream URL + headers + body → stream back**. Base-URL precedence: **BYOK cred
  baseUrl > env override > default**. Adding a provider = a registry entry + transforms, **not new
  handler code**. (Keep the *pattern* lean — llmgateway's real core is thousands of lines; ours won't be.)
  The registry is the **full catalog**; **env then org** narrow which providers/models are actually
  available (§0b).
- **Model catalog:** known models per provider (pricing + context window — the `models` table); drives
  cost + routing. Concrete models in v1; logical aliases deferred.
- **Streaming:** Hono native `streamSSE` passthrough; a **tee** captures the final `usage` block
  (OpenAI last chunk w/ `stream_options.include_usage`; Anthropic `message_delta`); tokenizer
  fallback if a provider omits usage. Client disconnect cancels upstream.

### B. Routing & resilience
- **Concrete models (v1):** clients send a concrete `model` (`{provider}/{model}`); the **routing
  policy defines the failover order**. (Logical **aliases deferred**.)
- **Routing policy:** each **app** has a `default_routing_policy` (allowed models + failover order +
  optional **credential pin**); an **org default** policy covers member keys with no app context. v1
  strategy = **priority (ordered)**; pluggable `Selector` → later `WeightedScoreSelector`
  (latency/cost/health) **without touching call sites**.
- **Failover / resilience (v1):** try candidates in order; **retry** on retryable errors (5xx,
  timeout, 429) with exponential backoff, then advance to the next candidate; **non-retryable** (4xx
  auth/invalid) returns immediately. Per-(provider, credential) **circuit breaker** (Redis error-rate
  window) skips a failing target for a cooldown. **No mid-stream failover** (only if no bytes
  streamed); `X-No-Fallback` header opts out.
- **Credential selection:** for the chosen `{provider, model}`, resolve a credential (**App → Org**);
  if several exist, pick a **healthy** one (skip invalid/expired/rate_limited).

### C. Tenancy, apps & access
- **Within a tenant: one org (the company).** Under it, **Teams and Apps are siblings**:
  - **Teams** hold people. **A member belongs to exactly one team.** The team is the layer that
    **sets budget & rolls up usage tracking**. Team role: `team_admin` / `member`.
  - **Apps** = things that consume the gateway; **apps are an attribution dimension, not a budget
    scope**. Three kinds:
    - **Predefined / system apps** — ship with Vortex; notably **Chat**, the built-in chat / LLM
      module the gateway manages. Seeded per org. **Chat's backend (gateway endpoints + predefined
      Chat app) is v1** — it's how we forward to and use models; the dedicated Chat **UI** comes later.
    - **User apps** — the org's own deployed services; each has its own app key, default routing
      policy, and provider bindings.
    - **Personal apps** — a member may declare one for their **own** attribution (bucket their
      personal-key usage by app); optional.
    - External agents (Claude Code / Codex) need **no registration** — they call the gateway with a
      **member key** (attributed to the member), optionally via a personal app or the built-in **Chat** app.
  - **Every system/service app auto-creates a paired *technical member*** (a non-human service
    account) that **belongs to a team** and has its own **per-member budget** — this is how an app's
    **autonomous / headless** work is budgeted. When an app works **on behalf of a user**, it instead
    uses that **user's default key** → the user's budget. (Personal apps need none — they're
    member-driven.)
  - Members belong to the one org; **no org switcher**.
- **App access = grant a Team OR specific Members** (`app_access`), with an app role:
  - `app_admin` — configure the app (routing / creds / budget) + view.
  - `app_member` — **view the app** + is **eligible to use a key through this app** (acting-app).
  - App access governs **visibility + key-eligibility**, NOT per-request runtime authz (that's the
    key + tag). A member sees only apps they're granted (directly or via a granted team).

### C1. API keys (simplified — owner + per-request app context)
- **Owner = a member** — a **human member** or a **technical member** (the per-app service account,
  see Apps). An "app service key" is just a key owned by that app's **technical member** —
  offboarding-safe (technical members are never a person). *(No separate "app owner"; owner is
  always a member, so budgets stay purely per-member.)*
- **Member keys:** every member is **auto-issued one default key** on joining; they may create
  more **personal keys** (for scoping / rotation). All behave the same.
- **No members×apps key sprawl.** User apps carry their **own app-owned keys**; a member keeps
  **one key** (default + optional personal) for personal use, external agents, and the built-in
  Chat. Key count scales as **members + apps**, not members × apps. *(Optional/advanced: a member
  key may pass an **acting-app tag** `x-vortex-app` to attribute usage to a user app it's granted
  on — honoured only if the member is in that app's access.)*
- **App keys:** an org-deployed app has its own app-owned key; per-person breakdown via the
  **acting-user tag** (`x-vortex-user`). Symmetric to acting-app.
- Common: mint / list / rotate (grace window) / revoke / disable; per-key allow-deny **rules**
  (models / providers / ip) + optional **rate limit**; keys are **not app-bound** (the default key
  serves all apps); hashed, `vtx_` prefix; Redis hot-lookup key → {org, owner_member_id, rules, status}.
- **Requires:** org always has a **default routing policy** + ≥1 **org-level provider credential**
  so keys with no app context always resolve.
- *Note:* both tags are app-asserted → fine for **attribution/reporting**; only the **key owner +
  app membership** are trusted for authz. Per-tag *enforcement* is a later budgeting decision.
- **Provider credentials (BYO):** a provider API key, scoped **Org / App** (team-scoped deferred);
  **AES-GCM encrypted at rest**, masked to last-4 after entry.
  - **Resolution at request time: App → Org** (app cred wins, else org default).
  - **Multiple creds per provider** (accounts / regions / quota pools); routing may **pin** one, else
    a **healthy** one is chosen. **Health:** test-connection → valid / invalid / expired /
    rate_limited + last-checked; unhealthy creds skipped in failover.
  - **Rotation** (zero-downtime, records rotated-at); **enable/disable** a provider or a single cred;
    **negotiated price override** (per-cred in/out prices override the public table for cost).
  - Managed by owner/admin (org creds) and **app_admin** (their app's creds).

### C2. RBAC (roles & visibility)
- **Org roles (authoritative — org role takes precedence over any team/app role):**
  - **owner** — sees & manages **everything** (all apps, teams, members, providers, budgets,
    billing, settings, danger zone).
  - **admin** — manages **members, teams, apps, providers, budgets**; **not** billing or org
    danger zone.
  - **member** — **no default app visibility**; sees only apps granted to them (directly or via a
    granted team) + their own keys & usage.
- **App role** (`app_admin` / `app_member`) refines only what a **plain member** can do on a
  granted app. **owner/admin override it** and see/configure every app inherently.
- **Effective permission:** org role decides first (owner/admin ⇒ full); for a member it's the
  app role on granted apps. Middleware guard enforces routes + key rules.

### C3. Reconciling keys ↔ attribution ↔ budgets
Three independent axes — the api_key is **not** the budgeting unit:
1. **Credential (key)** — authenticates the caller (owner + rules). A member may hold **many keys**;
   keys are **not app-bound** (default key serves all apps).
2. **Attribution** — every `usage_record` carries **team_id, member_id, api_key_id, app_id?**
   (app_id null for pure personal use unless a personal app is declared) → admin slices usage by
   **team / member / app / api_key / model**.
3. **Budget** — enforced at the **member** level only (team default, overridable). **One ceiling
   per request** → trivial to reason about.
**Result:** many keys, many apps, still **one budget** per member; team/app/key are just reporting
granularities.

### D. Usage, cost & governance (the moat)
- **Usage records:** per request — provider, model, tokens, `cost_micro_usd`, status, `latency_ms`,
  `ttfb_ms`, plus all attribution ids; idempotent on `request_id`; monthly partitioned.
- **Cost calc:** `models` price table keyed `provider+model+effective_at`;
  `cost = prompt/1000×in + completion/1000×out`; provider `usage` → tokenizer fallback;
  per-credential **negotiated price override** wins when present.
- **Budgets — per member, monthly (simple):** each member has **one effective monthly ceiling** =
  their **team's default-per-member** budget, unless given a **per-member override**. It applies
  across **all apps**. **Apps & keys are attribution only** — they show *where* the budget went,
  they don't cap. **hard** → block (402) when the member is over; **soft** → alert-only. Org total =
  **sum of member budgets** (governed via teams; reportable, not a separate cap in v1). Owner/admin
  set team defaults; **team_admin** may set overrides within their team. Reset on the 1st.
- **Audit log:** append-only, **hash-chained** (`prev_hash`/`entry_hash`), tamper-evident, via outbox.
- **Dashboard / admin analytics:** usage & cost **sliceable by team / member / app / api_key /
  model** (multiple granularities), key management, budget config (team defaults + member
  overrides), audit viewer.

### D1. Dashboard IA (grouped, navigation-first — uses the existing kouji-ui design system)
Two role-gated surfaces; each hub groups related **analytics + management** with drill-down.
- **Admin (owner/admin):** Overview · **Usage & Budgets** (cost explorer sliceable by team/
  member/app/key/model **+** team-default & per-member budgets) · **Teams & Members** (teams +
  members/roles + **each member's keys**; human & technical) · **Apps** (per-app tabs: Access/
  Routing/**Keys**/technical member/Usage) · **Providers & Models** (creds + catalog) · **Audit
  & Alerts** (hash-chain log + anomalies) · **Billing** (SaaS only — plan / invoices / payment via
  Stripe portal) · **Settings**. *(No standalone Keys hub — member keys live under Members & Roles,
  technical/service keys under each App.)*
- **Member:** Home · My Usage & Budget · My Keys (default + personal) · My Apps · **Chat**
  (backend v1, UI later) · Profile.
- **Platform (SaaS super-admin, `multi` mode only):** tenant-orgs list, provision / suspend, plans,
  cross-tenant usage & health. Separate from any org's console.

### D2. Platform console IA (SaaS super-admin — `multi` mode only)
A **separate surface** for **vendor staff** (`platform_admins`), above all tenant orgs — same
grouped, navigation-first philosophy. **v1 = essentials:**
- **Overview** — platform KPIs: tenants (active/suspended), total usage/spend, requests/tokens,
  new tenants, top tenants, system health.
- **Tenants** — list all orgs (plan / status / owner / members / apps / month spend); **provision /
  suspend / reactivate / delete + data purge**; per-tenant: Overview · Members (owner/admins) ·
  Usage · **assign Plan & limits**.
- **Usage** — cross-tenant usage sliced by **tenant / plan / provider / model** + anomalies.
- **Billing** — subscriptions, revenue / MRR, invoices, **plans ↔ Stripe prices** (Stripe-backed).
- **Plans & Entitlements** — define tiers (limits: members, spend, features, rate limits); assign.
- **Platform Admins** — vendor staff + roles (`platform_owner` / `platform_admin` / `support`).
- **Audit** — platform audit log (all super-admin actions, hash-chained).

**Deferred (phase 2):** **Support view-as / impersonation** (audited), global **Providers & Models**
management (seed a default catalog initially), platform-wide **Alerts**, **Settings** (feature flags
/ white-label / announcements).

### E. Billing & subscriptions (Stripe — SaaS `multi` mode only)
Enterprise / on-prem (`single`) installs are **licensed by contract — no Stripe**. In SaaS:
- **Each tenant org = a Stripe Customer + a Subscription** to a **plan** (`plans` ↔ Stripe Price).
- **Stripe-hosted Checkout + Customer Portal** — **card data never touches our servers** (PCI stays
  with Stripe). Org owner manages payment method / invoices / upgrade-downgrade in the portal.
- **Webhooks** (signature-verified, idempotent) sync subscription status → **org lifecycle**:
  `active` ok · `past_due` → warn · `canceled`/unpaid → **suspend org** (gateway blocked).
- **Entitlements** enforced from the subscribed plan's `limits` (members, spend cap, features, rate limits).
- **Surfaces:** Platform **Billing** (subscriptions, revenue/MRR, plans↔Stripe prices); Org console
  **Billing** (plan, invoices, payment method, upgrade — all via the Stripe portal).
- **Billing model: TBD → remodel later.** We like **llmgateway's pricing logic** — captured here as
  the reference to model Vortex's own pricing from (likely enterprise-first: platform subscription
  for BYOK/enterprise + optional managed-usage fee):
  - **Managed (pay-as-you-go credits):** top up a credits wallet, **deduct per request at provider
    rates**, **+~5% fee at top-up**. Variable, transparent markup, no cap. Margin = the 5%.
  - **BYOK:** client's own provider key → provider bills them directly → **no credits, 0% fee**;
    monetize only via a subscription (if any).
  - **Pro (feature subscription):** flat monthly unlocking features (rate limits / retention);
    **stacks on top** of managed usage (sub + fee run in parallel — not a usage plan).
  - **DevPass-style (usage bundle):** flat monthly with a **usage allowance** (e.g. $1 paid → ~$3 of
    provider-rate usage), metered vs a cap, **reset monthly**; **replaces** the per-request fee —
    margin is the spread (prompt caching, volume/wholesale discounts, breakage). Loses on heavy users,
    profits on light users + unused allowance.
  - **Enterprise:** custom, **contract / invoiced** — not self-serve Stripe.

## Architecture

### Backend structure (Hono — route groups + service layer, no heavy DI)
- **Route groups:** `/v1/*` (gateway proxy) and `/api/*` (dashboard: auth, orgs, teams, apps,
  keys, usage, budgets, audit).
- **Gateway middleware chain:** `apiKeyAuth → resolveContext(app/user tags) → rbacScope →
  budgetGuard → route/select → proxy → recordUsage → commitSpend → audit`.
- **Service layer** (`packages/core`, plain TS): `GatewayService`, `RoutingService`,
  `ProviderRegistry` + adapters, `ApiKeyService`, `CredentialService`, `BudgetService`,
  `UsageService`, `CostService`, `OrgService`, `AppService`, `RbacService`, `AuditService`.
- **`packages/db`** — Drizzle schema + migrations (+ `drizzle-zod`). **`packages/shared`** — **Zod
  schemas + inferred DTOs/types** shared with
  the Angular app. **`packages/sdk`** — thin helpers only (on-behalf-of fetch, acting-user/acting-app
  tag headers); **primary integration = point the existing OpenAI / Anthropic SDK at our base URL**
  (no proprietary SDK).

### Drizzle schema (core tables)
`organizations` (**tenant**; `plan`, `status enum[active,suspended]`, `default_routing_policy` jsonb,
`created_at`),
`platform_admins(user_id, role enum[platform_owner,platform_admin,support])` (vendor staff, above
orgs; `multi` mode only),
`plans(id, name, limits jsonb, stripe_price_id?, price?)` (org.plan → plans),
`subscriptions(org_id, stripe_customer_id, stripe_subscription_id, plan_id, status, current_period_end,
cancel_at?)` (SaaS only; webhook-synced),
`platform_audit_logs(platform_admin_id, action, target_org?, metadata, prev_hash, entry_hash)`
(hash-chained; logs impersonation / view-as),
`teams(org_id, default_member_budget_micro, budget_enforcement enum[hard,soft])`,
`apps(org_id, kind enum[system,service,personal], owner_member_id? (personal apps),
technical_member_id? (auto service account for system/service apps), default_routing_policy)`
(Chat seeded per org as kind=system), `users(sso_subject)`,
`memberships(user_id? (null for technical), org_id, type enum[human,technical],
role enum[owner,admin,member]? (null for technical), team_id?, team_role enum[team_admin,member]?,
budget_override_micro?)`
(member ∈ ≤1 team; technical = per-app service account; `budget_override` beats the team default),
`app_access(app_id, principal_type enum[team,member], principal_id, role enum[app_admin,app_member])`
(grant a team OR a member),
`api_keys(org_id, owner_member_id → memberships (human or technical), is_default bool, key_hash uniq,
key_prefix, rate_limit?, status, expires_at, created_by, last_used_at)` (owner always a member; not app-bound),
`api_key_rules(api_key_id, rule_type enum[allow_models,deny_models,allow_providers,ip_cidrs,…],
rule_value jsonb)`,
`provider_credentials(org_id, scope_type enum[org,app], scope_id, provider, label?, region?,
encrypted_key, price_override?, health_status enum[valid,invalid,expired,rate_limited],
last_checked_at, rotated_at?, enabled bool)`,
`models(provider, model_name, input_price_per_1k, output_price_per_1k, context_window, effective_at)`,
`usage_records(request_id uniq, org_id, api_key_id, member_id (human|technical), app_id?, team_id?,
acting_user_id?, provider, model, tokens…, cost_micro_usd, status, latency_ms, ttfb_ms, created_at)`
— tagged with all attribution dims so any scope rolls up,
(**no separate budgets table** — budget = `teams.default_member_budget` + optional
`memberships.budget_override`, enforced monthly per member),
`audit_logs(org_id, actor, action, target, metadata, prev_hash, entry_hash)`.
Relations: org 1─N team/app/member/apikey/credential/usage; **team 1─N member** (member ∈ exactly
one team); **app N─N (team|member)** via `app_access`; app 1─N apikey/usage; member 1─N apikey/usage.
Everything carries `org_id`.

### Reference: how llmgateway models this (and where Vortex differs)
llmgateway is **flat**: `organization → project → api_key`, **no team table** ("team" = org),
**org-only roles** (owner/admin/developer; project membership presence-only), keys **always
project-scoped**, provider creds **org-only**, budgets at org/member/key. Vortex adds the
enterprise layer they lack: **first-class Teams (one team per member)**, **Apps with team/member
grants + a technical member each**, **member-owned keys (human + technical)** with acting-app/
acting-user tags (no members×apps sprawl), **app/org-scoped provider creds**, and **per-member
monthly budgets (team-defaulted, overridable)**. We borrow their per-key IAM-rule table.

### Gateway request lifecycle
1. **Key auth** — hash header key → Redis lookup → reject if missing/expired/revoked.
2. **Resolve context** — from key owner + `acting-app`/`acting-user` tags derive {org, member_id,
   app_id (validated vs `app_access`), team_id, rules}.
3. **Scope/RBAC** — key rules allow model/endpoint?
4. **Budget pre-check** — the **member** is the key's owner (human, or the app's technical member);
   for on-behalf-of the app uses the user's own key → that human. Check their **effective monthly
   ceiling** (override ?? team default) via **org-scoped** Redis counter
   `spend:{org}:member:{id}:{month}`; if **hard** & exceeded → **402**. Estimate = `max_tokens × price`;
   INCR a **reservation** to stop burst overrun.
5. **Route/select** — resolve routing policy + credential from the **app** (app context) or **org
   defaults**; `RoutingService` picks primary.
6. **Proxy + stream** — adapter forwards; failover only if no bytes streamed.
7. **Record usage** — parse tokens, compute cost, insert `usage_record` (idempotent) with all ids.
8. **Commit spend** — replace reservation with actual cost; enqueue reconcile.
9. **Audit** — append hash-chained entry via outbox.

### Spend-cap enforcement (race-safe)
- **Pre:** one Redis GET vs cached ceiling; INCR reservation for estimated max, released on completion.
- **Post:** real cost replaces reservation; persist `usage_record`.
- **Reconcile:** periodic job re-sums `usage_records` → authoritative Redis counter; reset on the 1st.

## Milestones (vertical, each shippable + testable)

1. **Skeleton + multi-tenant foundation + auth** — pnpm monorepo, Hono bootstrap, Postgres/Redis,
   Drizzle schema + migrations, **env-driven config layer** (`TENANCY_MODE`, enabled providers +
   base URLs, flags — validated at boot), **strict `org_id` isolation (app-level scoping + Postgres
   RLS)**, **org provisioning** (single: seed one org; multi: signup → new org, first user = owner),
   user auth, team / app CRUD + `app_access` grants, **auto-issue each member's default key + each
   app's technical member**, Angular SSR login + shell (kouji-ui, no org switcher).
2. **Proxy MVP** — OpenAI provider adapter, keys (member + technical), **non-streaming**
   `/v1/chat/completions` + `/v1/models` + `/v1/embeddings`, `usage_record` + cost + acting-user tag. E2E testable.
3. **Streaming + multi-format + multi-provider** — SSE + usage tee; **inbound `/v1/messages`
   (Anthropic → Claude Code) + `/v1/responses` (OpenAI Responses → Codex)** + cross-format transform;
   Anthropic + Google provider adapters.
4. **Routing resilience** — ordered failover, retries, circuit breaker.
5. **Governance (the moat)** — **per-member monthly budgets** (team default + overrides; Redis
   reserve + reconcile), RBAC guards (org roles authoritative + app grants), hash-chained audit log.
6. **Dashboard** — usage/cost charts (per member / app / model), key management, budget config,
   audit viewer (Angular + kouji-ui).
7. **Platform console (SaaS, essentials)** — vendor super-admin: tenant provision / suspend / delete,
   plans & entitlements, cross-tenant usage, platform admins + audit (Angular + kouji-ui). View-as,
   global provider mgmt, alerts, settings → phase 2.
8. **Billing (Stripe, SaaS)** — org ↔ Stripe Customer + Subscription (plans ↔ Stripe prices),
   Stripe-hosted Checkout + Customer Portal, signature-verified **webhooks → org lifecycle** (suspend
   on unpaid); platform **Billing** hub + org **Billing** page. `single`/on-prem installs skip this.

## Top risks / hardest parts
1. **Accurate token/cost capture across streaming + 3 providers** (differing `usage` semantics).
2. **Race-free hard-cap enforcement under concurrency** (reserve + reconcile).
3. **Mid-stream failover** without double-charging or corrupting SSE.
Other: credential encryption, audit immutability, provider API drift, tag-authz (validate acting-app
vs access), **technical-member lifecycle** (auto-create/retire with the app; default team + budget).

## Verification (per milestone, end-to-end)
- **Proxy:** real `curl` with a `vtx_` key vs a fake/echo provider AND one live provider; assert
  OpenAI-shaped response + a `usage_record` with correct micro-USD cost.
- **Streaming:** consume SSE, assert incremental chunks + final `usage` captured.
- **Failover:** force primary 5xx (mock) → fallback fires, exactly one usage row.
- **Hard cap:** set a member's monthly budget tiny + fire concurrent requests → their spend never
  exceeds it (402 once full); a per-member override beats the team default; Redis reconciles to DB.
- **Granularity:** admin can slice the same usage by team / member / app / api_key / model.
- **Tenant isolation:** a request/query in org A can never read org B's data (keys, usage, budgets,
  creds); Redis counters are org-namespaced; provider-cred decryption is per-org.
- **Access:** a member sees only granted apps; `acting-app` tag rejected when member not in app_access.
- **No sprawl:** one member key + acting-app tag produces correct per-app rollups across ≥2 apps.
- **Audit:** hash chain intact + append-only.
- **E2E (Angular):** login → create org/app → grant a member → default key present → view usage/cost
  → set monthly budget, through the browser UI (Playwright).
