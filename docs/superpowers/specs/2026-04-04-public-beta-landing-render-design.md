# Public beta, landing site, and Render deployment — design

**Status:** draft — pending product review  
**Date:** 2026-04-04  
**Related:** [Auth — Microsoft Entra](./2026-03-22-auth-entra-design.md) (enterprise path; remains supported in parallel), [spec index](./README.md)

---

## Product intent

Ship a **Product Hunt–ready public beta**: a **separate marketing site** (own domain), a **hosted product** on **Render**, and **self-serve sign-in** via **Google**, **GitHub**, and **email magic link**—implemented **in-house** (no managed B2C vendor for v1). **Enterprise** customers continue toward **organization + Microsoft Entra** (or similar) as a **later phase**, sharing the same long-term **user / tenant** model.

**Success criteria (beta)**

- A stranger can complete **sign-up or sign-in** with **any** of the three methods and use core product flows (chat, KB, etc.) on production.
- **Landing** and **app** deploy independently; landing **never** depends on product session cookies.
- **Staging** mirrors production enough to validate **OAuth redirect URIs** and **CORS** before launch.

---

## Out of scope (this design)

- **Stripe / paid plans** — not required for PH beta; add under a separate billing spec.
- **Full multi-tenant enterprise** (org admin, SSO for every customer) — **Phase 4**; Entra slice remains as today until extended.
- **Celery / async ingest** — product already defers this; deployment does not assume workers beyond API.
- **Shared auth cookie between unrelated apex domains** — not a goal; landing stays unauthenticated for v1.

---

## Architecture

### Identity spine

- **One internal user record** (existing `users` table direction); **external identities** stored as **linked accounts** (provider + stable subject + optional email snapshot), not parallel user silos per provider.
- **`AUTH_MODE`** evolves to include a **consumer OIDC + magic-link** path while **preserving `AUTH_MODE=entra`** for enterprise deployments and future org flows.
- **Landing** host serves **marketing only**; **all** sign-in/up UI lives on the **app** origin so OAuth `state`/PKCE and redirects stay on one site.

### Consumer authentication (v1)

1. **Google and GitHub:** Authorization code flow with **PKCE**. **Browser** starts the flow from the **app**; **token exchange** runs on the **API** using **client secrets** (callbacks hit the API host, not the SPA bundle).
2. **Magic link:** API creates a **short-lived, single-use** token (stored **hashed**), sends email via a **transactional provider**; user follows a link whose **hostname** is the **app** (or API redirect-to-app pattern—choose one implementation and keep URLs stable per environment).

### Session and tokens (deployment-dependent default)

- **Preferred when practical:** **short-lived access JWT** sent as **`Authorization: Bearer`** from the SPA, plus **refresh** via **http-only cookie** where **CORS**, **origins**, and **cookie `Domain`** can be configured consistently (e.g. `app.example.com` + `api.example.com` under the same registrable domain).
- **When app API and SPA are on unrelated apex domains:** use **Bearer-only** with **short TTL** and **re-authentication** rather than fragile cross-site cookies; document the two **Render templates** (shared parent domain vs split apex) in the implementation plan.

### Enterprise authentication (later)

- **Entra:** Continue validating JWTs per [Entra design](./2026-03-22-auth-entra-design.md); **converge** on the same **user resolution** layer (e.g. upsert by `oid` + `iss`, org/tenant claims when added). No requirement to remove SPA Bearer model for Entra in the first consumer slice.

### Account linking (v1 policy)

- **Auto-link:** If an OAuth provider returns a **verified email** that matches an **existing user’s** primary email, **attach** the new provider identity to that user.
- **Otherwise:** **Create** a new user for that provider subject.
- **Ambiguous cases** (same person, different emails across providers): **out of scope for v1**; support handles manually or user uses a single provider until a dedicated “merge accounts” flow exists.

---

## Components and repository layout

| Area | Location | Notes |
|------|----------|--------|
| Product app | `frontend/` | Existing TanStack Start app; sign-in/up routes, post-login shell. |
| Landing | `landing/` | **New** app, **same stack** as `frontend/` (TanStack Start, Vite, Tailwind). |
| API | `backend/` | OAuth callbacks, magic link, email, JWT/session issuance, identity tables. |
| Infra | `render.yaml` (to be added) | Postgres + API + frontend + landing services; env groups as needed. |

**Landing content (v1)**

- Value proposition, screenshots or product captures, **primary CTA** → `VITE_APP_URL` (configurable).
- Legal/footer: **Privacy** and **Terms** (can be routes on landing or app—pick one place and link consistently).
- **No** required calls to authenticated product APIs.

**Domains**

- **Landing:** dedicated **apex or www** domain.
- **App:** either **another domain** or a **subdomain** of the landing domain (e.g. `app.example.com`). OAuth and CORS configuration must list the **app origin** explicitly.

---

## Data flow (summary)

1. User on **app** clicks Google/GitHub → redirect to IdP → redirect to **API** callback → API upserts user + link → issues session tokens → redirect to **app** success route.
2. User on **app** requests magic link → API rate-limits, stores hashed token, sends email → user opens link on **app** (or via API redirect) → API validates → same session issuance as OAuth.
3. **Landing** user clicks “Open app” → navigates to **app** sign-in or home; **no** cross-domain session.

---

## Error handling and abuse

- **OAuth cancel / error:** Redirect to app sign-in with safe, short message; **no** internal details.
- **Invalid `state` / PKCE failure:** Generic failure + server-side logging with **correlation id**.
- **Magic link invalid/expired/used:** Clear copy; same user-facing shape for unknown tokens (**no** enumeration where feasible—use “If an account exists…” for **request** endpoint).
- **Rate limits:** Per-IP and per-email cooldowns on magic-link **request**; light limits on callback endpoints.
- **API errors:** Consistent **401/403** JSON; SPA redirects expired sessions to sign-in.

---

## Testing

- **Unit:** Token hashing, TTL, linking rules, JWT/session creation.
- **Integration:** Mocked IdP token/userinfo exchange; magic-link flow with test fixtures.
- **E2E:** Staging or dev-only fixtures; do not weaken production security for tests.
- **Render:** **Staging** stack with real OAuth app **redirect URIs** for staging URLs.

---

## Phased roadmap

| Phase | Goal |
|-------|------|
| **0 — Render skeleton** | Managed Postgres; deploy API, `frontend/`, `landing/`; migrations; health checks; staging + prod; custom domains. |
| **1 — Consumer auth** | Google + GitHub OAuth + magic link; identity persistence; wire `frontend/` auth UI; CORS and redirect URIs for all deployed origins. |
| **2 — Beta hardening** | Stabilize core product paths; logging/alerts; privacy/terms; support channel; optional status banner. |
| **3 — Product Hunt** | Landing polish, assets, demo narrative, launch-day monitoring. |
| **4 — Enterprise** | Org/tenant admin, Entra-first SSO for customers, authorization aligned to org boundaries (extends existing Entra work). |

---

## Self-review notes (2026-04-04)

- **Placeholders:** OAuth client registration steps are generic by necessity; implementation plan will name concrete env vars and Render service names.
- **Consistency:** Entra doc assumes SPA Bearer for MVP; consumer path may use refresh cookies **when domain layout allows**—both coexist under explicit `AUTH_MODE` / deployment docs.
- **Scope:** Single spec for landing + deploy + consumer auth + roadmap; implementation should still be split into **tickets** (deploy vs auth vs landing content).
- **Ambiguity resolved:** Account linking v1 = **verified-email auto-link**; magic links are **single-use, short TTL, stored hashed**.

---

## Open items (for implementation plan, not blockers for this design)

- Exact **transactional email** vendor and **from** domain (SPF/DKIM).
- Whether magic-link verification is **API-hosted redirect** vs **app route** that calls API (either is fine if URLs are stable).
- Whether `landing/` gets its own **Dockerfile** copy of `frontend`’s pattern or a **shared base image**—implementation choice.
