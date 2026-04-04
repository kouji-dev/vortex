# SaaS + Multi-Tenancy + Auth Overhaul — Design Spec

**Date:** 2026-04-05
**Status:** spec-approved
**Scope:** Sub-projects 1–3 of the SaaS/self-hosted transformation

---

## Overview

Transform AI Portal from a single-user/Entra-only deployment into a product that supports:

- **SaaS mode** — open signup for individuals and organizations, hosted by you
- **Self-hosted mode** — enterprise-deployed single-org instance, invite-only

This spec covers three sequential sub-projects:

| # | Sub-project | Depends on |
|---|-------------|-----------|
| 1 | Auth overhaul (fastapi-users, email/password, JWT) | nothing |
| 2 | Multi-tenancy core (org model, tenant isolation) | Auth |
| 3 | Deployment modes (SaaS vs self-hosted config, setup wizard) | Multi-tenancy |

Billing/subscriptions are out of scope for this spec (planned as a separate phase).

---

## Sub-project 1: Auth Overhaul

### Approach

Replace `AUTH_MODE=entra` / `AUTH_MODE=dev` with [`fastapi-users`](https://fastapi-users.github.io) — a battle-tested FastAPI auth library that provides:

- Email/password registration and login
- JWT access + refresh tokens (stateless, no Redis session required)
- Email verification and password reset
- Built-in OAuth2 social login hooks (Google, GitHub — phase 2)

### Deployment mode env var

`AUTH_MODE` is replaced by `DEPLOYMENT_MODE` (the old var name is kept as an alias during transition):

| Value | Behavior |
|-------|----------|
| `saas` | Open signup enabled; personal org auto-created on registration |
| `selfhosted` | Signup disabled; first-run setup wizard required; invite-only after setup |
| `dev` | Kept for local development; fixed bearer token, seed user — no change |

`AUTH_MODE=entra` remains functional during a transition period. A migration guide documents how to move existing Entra users into the new user table.

### Auth endpoints

```
POST /auth/register          — create account (saas or invite token)
POST /auth/login             — email + password → JWT access + refresh tokens
POST /auth/refresh           — exchange refresh token for new access token
POST /auth/verify            — email verification (token from email)
POST /auth/forgot-password   — trigger password reset email
POST /auth/reset-password    — complete password reset
GET  /auth/me                — current user identity
```

`/api/me` is retained for portal-specific profile data (memories, portal API keys). Auth identity lives at `/auth/me`.

### JWT payload

```json
{
  "sub": "<user_id>",
  "org_id": "<org_id>",
  "role": "owner | admin | member",
  "exp": "<timestamp>"
}
```

`org_id` and `role` are embedded at login so downstream services don't need DB lookups per request.

### SSO (phase 2)

`fastapi-users` has first-class OAuth2 support. Google and GitHub can be added as config-driven providers. SAML for enterprise SSO (via `python3-saml` or WorkOS adapter) is a separate future phase.

### Backward compatibility

- `AUTH_MODE=dev` continues to work unchanged for local development
- `AUTH_MODE=entra` continues to work during migration
- Existing routes protected by `current_active_user` dependency are unchanged — only the user source changes

---

## Sub-project 2: Multi-Tenancy Core

### Data model

#### `orgs` table (new)

```sql
CREATE TABLE orgs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug          TEXT UNIQUE NOT NULL,
    name          TEXT NOT NULL,
    instance_mode BOOLEAN NOT NULL DEFAULT false,  -- true for self-hosted single-org
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`instance_mode = true` marks the single org created by the self-hosted setup wizard.

#### `users` table (new — replaces seed user / Entra-derived user)

Managed by `fastapi-users`. Extended with:

```sql
ALTER TABLE users ADD COLUMN org_id UUID NOT NULL REFERENCES orgs(id);
ALTER TABLE users ADD COLUMN role   TEXT NOT NULL DEFAULT 'member'
    CHECK (role IN ('owner', 'admin', 'member'));
```

**One user, one org.** A user belongs to exactly one org. Accepting an invite to a different org migrates the account (personal org is archived). Users who want to participate in multiple orgs use separate accounts.

#### Tenant-scoped tables

The following existing tables receive `org_id UUID NOT NULL REFERENCES orgs(id)`:

- `assistants`
- `conversations`
- `knowledge_bases`
- `documents`
- `memories`
- `model_catalog` (org-level overrides; global defaults remain unseeded per-org)
- `portal_api_keys`

#### Migration strategy

A single Alembic migration:
1. Creates the `orgs` table
2. Inserts a default org (`slug = 'default'`)
3. Adds `org_id` columns to all tenant-scoped tables with a default pointing to the default org
4. Drops the default constraint (column becomes required going forward)

Existing deployments keep all data intact under the default org.

### API tenant isolation

Every authenticated request resolves `org_id` from the JWT via a FastAPI dependency:

```python
async def get_current_org(user: User = Depends(current_active_user)) -> UUID:
    return user.org_id
```

All DB queries on tenant-scoped tables pass `org_id` through a base `TenantRepository`:

```python
class TenantRepository(Generic[T]):
    async def all(self, org_id: UUID) -> list[T]: ...
    async def get(self, id: UUID, org_id: UUID) -> T | None: ...
    async def create(self, data: dict, org_id: UUID) -> T: ...
    async def update(self, id: UUID, data: dict, org_id: UUID) -> T: ...
    async def delete(self, id: UUID, org_id: UUID) -> None: ...
```

There is no code path that queries a tenant-scoped table without `org_id`. Cross-org access is structurally prevented.

### Superuser / instance admin

Users with `is_superuser = True` (fastapi-users built-in flag) can query across orgs. The superuser flag is:
- Never settable via API
- Set only via a CLI management command (`python -m ai_portal.cli make-superuser <email>`) or the self-hosted setup wizard (first owner is superuser)

---

## Sub-project 3: Deployment Modes & Org Management

### Org management API

```
GET    /api/orgs/me                — current org info
PATCH  /api/orgs/me                — update name, slug (owner/admin only)
GET    /api/orgs/me/members        — list members with roles
DELETE /api/orgs/me/members/{id}   — remove member (owner/admin only)
PATCH  /api/orgs/me/members/{id}   — change member role (owner only)
POST   /api/orgs/me/invites        — create invite (sends email with token)
GET    /api/orgs/me/invites        — list pending invites
DELETE /api/orgs/me/invites/{id}   — revoke invite
POST   /auth/accept-invite         — accept invite token → register or migrate account
```

### Invite flow

1. Owner/admin calls `POST /api/orgs/me/invites` with `{email}`.
2. Backend creates a signed invite token (short-lived, e.g. 7 days) and sends an email with a link to `/org/invites/accept?token=...`.
3. If the invitee has no account: the accept page shows a registration form. On submit, their account is created scoped to the inviting org.
4. If the invitee already has an account (SaaS): they are prompted to migrate. On confirm, their `org_id` is updated, their old personal org is archived (soft-deleted — `orgs.archived_at` timestamp set, no data deleted).

### Self-hosted first-run wizard (`DEPLOYMENT_MODE=selfhosted`)

On first boot with no orgs in the DB, the app enters **setup mode**:
- All API routes return `503 Setup Required` except `GET /health` and `POST /setup`
- `POST /setup` accepts `{org_name, admin_email, admin_password}`, creates the instance org (`instance_mode = true`), creates the owner user (superuser), exits setup mode
- Setup mode is detected by `SELECT COUNT(*) FROM orgs` at startup; once > 0, setup endpoint is disabled

### Frontend pages

| Route | Description |
|-------|-------------|
| `/setup` | First-run wizard (selfhosted only, redirects away once setup complete) |
| `/login` | Email + password login |
| `/register` | Account creation (saas mode or invite token) |
| `/org/settings` | Org name, member list, invite management |
| `/org/invites/accept` | Invite acceptance (register or migrate) |

The existing dev-token flow (`VITE_DEV_TOKEN`) continues to work for local development.

---

## What is out of scope

- Billing, subscription plans, payment processing (separate phase)
- SAML SSO (phase 2, after OAuth2 social login)
- Multi-org membership per user (one user, one org by design)
- Workspace/team sub-grouping within an org (future)
- Admin console beyond basic org management (future)
- SCIM provisioning (future enterprise phase)

---

## Implementation order

Each sub-project is implemented in sequence. They can each have their own `writing-plans` implementation plan:

1. **Auth overhaul** — fastapi-users integration, new user table, login/register endpoints, JWT with org_id, dev/entra compat
2. **Multi-tenancy core** — orgs table, tenant_id on all tables, Alembic migration, TenantRepository, API isolation
3. **Deployment modes** — DEPLOYMENT_MODE config, setup wizard, org management API + UI, invite flow, frontend auth pages
