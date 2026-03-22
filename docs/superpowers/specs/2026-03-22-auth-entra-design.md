# Auth & authorization — Microsoft Entra ID (single-tenant MVP)

**Status:** approved for implementation planning  
**Date:** 2026-03-22  
**Related:** [Chat conversations spec](./2026-03-22-chat-conversations-design.md) (chat requires authenticated API access)

---

## Product intent

Ship a **vertical slice** so the AI Portal can identify **real users** from a customer’s **Microsoft Entra ID** tenant, enforce **coarse RBAC** from **Entra app roles** embedded in access tokens, and enforce **resource ownership** in the application database (e.g. `user_id` on conversations). This replaces the current **dev-only** bearer token that maps all requests to a seeded user.

**Out of scope for this slice**

- Multi-tenant SaaS (many Entra tenants on one deployment) — validate `tid` later.
- Second identity provider (Keycloak, etc.) — keep validation code structured for a future adapter; only Entra is configured.
- **User-delegated Microsoft Graph** (OBO, full group expansion when tokens hit **group overage**) — add when a product feature needs “as this user” Graph access or complete group lists not in the JWT.
- Cookie/BFF session model — MVP assumes **SPA + Bearer access token** for the API (no `HttpOnly` session cookie for the SPA in v1).
- **Implementing** backend callers to Azure APIs is **specified below** but may ship **after** interactive login works; first integration chooses Graph vs ARM vs storage.

**Alignment with product catalog ([spec index](./README.md)):** this slice delivers the concrete **MVP-1 identity** path for **single-tenant Entra** while staying compatible with **I-01** (OIDC connector framework), **I-04** (RBAC via app roles), and **I-06** (service / machine identity for jobs — see **Org-wide & background access** below).

---

## Architecture

### Authentication

1. **SPA** uses **Authorization Code + PKCE** against Entra (public client app registration).
2. SPA requests an **access token** whose **audience** is the **API** app registration (delegated scope exposed by the API, e.g. `api://<api-app-id>/access_as_user`).
3. **API** validates JWTs: signature (JWKS), `iss`, `aud`, `exp`, and for single-tenant **`tid`** matches configured tenant id.
4. **User provisioning:** stable directory object id **`oid`** (when present) plus `iss` uniquely identifies a person. **Upsert** into `users` on each authenticated request (or first request) using email/upn/preferred_username from claims for display and uniqueness fallback.

### Authorization

| Layer | Source | Use |
|--------|--------|-----|
| **Coarse RBAC** | Entra **app roles** → `roles` claim on access token | e.g. `Admin`, `User`; enforced via FastAPI dependencies |
| **Fine (resources)** | PostgreSQL: `user_id` (owner) on rows | list/filter by owner; get-by-id checks owner unless admin override is explicitly coded |

Entra does **not** store portal resources; it only supplies identity and directory-assigned roles.

### Backend → Microsoft Azure APIs (separate from “user hits FastAPI”)

The SPA authenticating users does **not** automatically give the API permission to call **Microsoft Graph** or other Azure data plane APIs. Those calls need their **own** Entra credentials. Use the pattern that matches **who** the API acts as:

| Pattern | When to use | Entra setup (summary) |
|--------|-------------|------------------------|
| **On-behalf-of (OBO)** | “As **this signed-in user**, read their profile / groups / Teams context.” | **API** app registration: **delegated** Graph permissions; **client secret** or **certificate** on that app; exchange the incoming user access token for a Graph access token server-side. |
| **Client credentials** | “As the **application** itself,” no user context (sync jobs, org-wide reads where policy allows). | Same or separate app registration: **application** permissions (or resource-scoped client creds); secret, cert, or **managed identity** when the API runs in Azure. |

**Managed identity** (Azure-hosted API) is preferred over long-lived secrets for **app-only** access to Azure resources (Storage, Key Vault, Azure OpenAI with Entra auth, etc.).

**Important:** The access token the SPA sends to your API is usually **audience-scoped to your API** (`aud` = your API). It is **not** automatically a Graph token. OBO (or a separate user flow for Graph scopes, rarely used for server-centric designs) is how the backend obtains **user-delegated** Graph tokens.

#### Org-wide & background access (cron, queues, “lazy” jobs)

For work that must run **with no signed-in user** (scheduled sync, batch indexing, org-wide directory reads), use **client credentials** with **application permissions** on an Entra app registration (often a **dedicated “worker”** app for least privilege, separate from the interactive API app).

- **No OAuth `offline_access` / refresh tokens** are required for this pattern: Entra typically returns **short-lived access tokens only** for the client-credentials grant; the backend **requests a new access token** when needed and may **cache it in memory** until expiry.
- **Admin consent** in the tenant grants the worker access to org data **only within the application permissions** configured — not “all data by default.”
- Maps to catalog capability **I-06** (service accounts / machine identity).

**Terminology:** “Offline” in the sense of **no user session** is satisfied by **app-only** access, not by storing user refresh tokens.

### Operational modes

- **`auth_mode=dev` (default for local):** existing `dev_bearer_token` + `dev_seed_user_email` behavior unchanged for tests and quick local dev.
- **`auth_mode=entra`:** require valid Entra JWT; no dev token bypass.

---

## Entra configuration (operator checklist)

1. **API app registration:** Application ID URI, expose **scope**, define **app roles** in manifest, enable tokens for the API.
2. **SPA app registration:** SPA platform, redirect URIs, **delegated** permission to the API scope, admin consent.
3. **Enterprise application** (API): assign users or **security groups** to **app roles** so `roles` appears in tokens.
4. Document in repo **env var mapping:** tenant id, API **audience** (often `api://...` or client id per validation library), SPA client id (frontend only).

---

## Data model

- **`users`:** nullable **`entra_object_id`** (partial unique index) for stable join to `oid`; **`email`** for UX and provisioning.
- **Local `roles` / `user_roles` tables removed** (migration `006_drop_roles`): coarse RBAC comes from the Entra access token **`roles`** claim (`get_app_roles` / `require_app_roles`). Re-introduce DB-backed roles only if a future product need (e.g. offline entitlements cache, reporting) justifies it.

---

## API surface (minimal)

- **`GET /api/me`** (or `/api/users/me`): returns authenticated user id, email, and **effective role names** derived from token (and eventually DB). Used to align UI with server truth.
- Existing routers (`assistants`, `chat`, `documents`) continue to use **`get_current_user`**; implementation switches on `auth_mode`.

---

## Frontend

- Add **MSAL React** (or equivalent) with SPA client id and authority `https://login.microsoftonline.com/<tenant>`.
- **All app routes are protected** for the authenticated product surface: unauthenticated users are sent to the **sign-in / auth portal** first (only Entra login and static public pages such as error/health remain outside, if any).
- Shared **HTTP client** (or TanStack Query defaults): attach `Authorization: Bearer <accessToken>` for the **API scope** on every backend request.

---

## Security notes

- API must validate **`aud`** matches this API, not the Graph or SPA client id.
- Do not accept client-supplied `userId` for authorization; always derive from token → DB user.
- Prefer **404** for cross-tenant resource access where appropriate to avoid leaking existence.

---

## Verification

- **Backend:** `ruff check src tests`, `pytest` (include tests for dev mode; Entra mode tested with mocked JWT or test keys where feasible).
- **Frontend:** `npm run build`.

---

## Future extensions

- Multi-tenant: allowlist of `tid`, issuer variants.
- `IdentityProvider` adapter interface: shared OIDC validation with Entra-specific settings module.
- **OBO helper** (in-memory or distributed cache keyed by user) for the first **user-delegated** Graph or Teams feature; **MSAL Confidential Client** on the API for `acquire_token_on_behalf_of`.
- **I-08 feature entitlements:** entitlements payload (e.g. on `/api/me` or dedicated endpoint) derived from roles + plan; enforce on privileged routes — not part of this Entra MVP slice but required before gating many catalog capabilities.

## Integrity notes (cross-feature)

- **Chat** ([chat spec](./2026-03-22-chat-conversations-design.md)) depends on this slice: same **Bearer** contract and **401/403** handling; conversations remain **user-owned** in the DB.
- **Delivery order** for MVP-3 is documented in the [spec index](./README.md) (**Registry integrity** + **C-01** / **C-02** catalog rows): **auth → conversations → assistants** is allowed without changing this Entra design.
- **Per-user API keys (I-05 / MVP-2):** when added, keys authenticate **to the API** as an alternative to Entra JWT for automation; policy for “key + Entra” vs “key only” must be decided then (not blocking this spec).
