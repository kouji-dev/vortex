# Control Plane — Design Spec

## Purpose

- [ ] Provide the shared substrate every other module depends on: tenancy, identity, authz, audit, metering, billing, settings, webhooks
- [ ] Buyer: CISO / Head of Platform / IT Director
- [ ] Without this module, no other module can run

## Module Boundary

### Owns

- [ ] `orgs`, `org_members`, `org_invitations`
- [ ] `teams`, `team_members` (org → team → user hierarchy)
- [ ] `users`, `user_sessions`, `user_mfa_factors`
- [ ] `idp_connections` (SSO config per org)
- [ ] `ldap_connections` (LDAP / AD direct-bind config, per-org or per-deployment)
- [ ] `auth_provider_config` (deployment-declared enabled strategies: password / social / directory / enterprise)
- [ ] `scim_endpoints`, `scim_tokens`
- [ ] `roles`, `role_permissions`, `permissions` (catalog)
- [ ] `actor_role_assignments` (user/key → role within org)
- [ ] `api_keys` (personal, service, scoped)
- [ ] `audit_events` (append-only)
- [ ] `usage_events` (metered)
- [ ] `quotas`, `budgets`, `budget_alerts`
- [ ] `webhooks`, `webhook_deliveries`, `webhook_event_types`
- [ ] `notifications`, `notification_channels`
- [ ] `org_settings`, `module_flags`
- [ ] `data_export_jobs`, `data_delete_jobs`

### Consumes from other modules

- [ ] None. Control Plane has zero peers.

### Exposed to other modules (internal contracts)

- [ ] `require_actor(request) -> Actor`
- [ ] `require_permission(actor, permission, resource) -> bool`
- [ ] `emit_audit(event_type, actor, resource, payload)`
- [ ] `emit_usage(unit, quantity, actor, resource, metadata)`
- [ ] `emit_webhook(event_type, payload, org_id)`
- [ ] `get_org_setting(org_id, key) -> value`
- [ ] `is_module_enabled(org_id, module) -> bool`
- [ ] `get_actor_teams(actor) -> list[Team]`
- [ ] `get_enabled_auth_strategies() -> AuthConfig` (deployment-declared providers for frontend bootstrap)

## Features — In Scope

### Tenancy

- [ ] Org create / rename / archive / delete
- [ ] Org slug (URL-safe) + display name
- [ ] Org-level region pin (single region only for v1)
- [ ] Soft-delete with 30-day recovery window
- [ ] Hard-delete cascade to all module data (GDPR-grade)

### Users & Membership

- [ ] User signup (email + password)
- [ ] Email verification (token, expiry)
- [ ] Password reset
- [ ] User profile (name, avatar, timezone, locale)
- [ ] Org invitation flow (token link, expiry, role on accept)
- [ ] Multi-org membership per user
- [ ] Member list, search, filter by role
- [ ] Remove member (revokes sessions + keys for that org)

### Teams (org → team → user hierarchy)

- [ ] Team create / rename / archive / delete within an org
- [ ] Team slug + display name + description
- [ ] Add / remove users to/from a team (a user may belong to multiple teams)
- [ ] Team-scoped role assignment (a user's role can differ per team)
- [ ] Per-team key count — aggregate how many API keys each team's members own (keys stay attached to individuals)
- [ ] Team-scoped usage stats + budgets/quotas (aggregate spend across the team's members, not only per user)
- [ ] Team list, search, member count
- [ ] Removing a user from a team drops their team attribution; their personal keys are untouched

### Authentication Strategies (deployment-configurable)

- [ ] Auth is config-driven, not mode-gated — deployment declares enabled providers in YAML/env; no `saas`/`selfhosted` switch in code
- [ ] Strategy kinds: `password`, `social` (consumer OAuth), `directory` (LDAP/AD bind), `enterprise` (SSO) — any combination per deployment
- [ ] Social OAuth login: Google, GitHub, GitLab (consumer sign-in — distinct from enterprise Google Workspace SSO)
- [ ] Self-hosted deployments may also enable social providers (not restricted to SSO)
- [ ] Public auth-config bootstrap endpoint — returns enabled strategies + provider list so the frontend renders the right login UI
- [ ] Frontend adaptive auth UI — login / signup renders only the strategies the deployment enables, driven by the bootstrap endpoint
- [ ] Single auth-provider abstraction spanning all four kinds (`password`, `social`, `directory`, `enterprise`) behind one interface

### SSO / Identity

- [ ] SAML 2.0 (SP-initiated + IdP-initiated)
- [ ] OIDC (Authorization Code + PKCE)
- [ ] Entra ID (preset OIDC config)
- [ ] Okta (preset SAML + OIDC)
- [ ] Google Workspace (preset OIDC)
- [ ] Just-in-time user provisioning on first SSO login
- [ ] Domain-bound SSO (auto-route `@acme.com` to Acme's IdP)
- [ ] Per-org "SSO required" enforcement
- [ ] Identity provider abstraction (`idp/protocol.py`, `idp/providers/<name>.py`)

### Directory — LDAP / Active Directory (direct bind)

- [ ] LDAP v3 bind authentication (user enters credentials into our login form; app binds against the directory to verify)
- [ ] Active Directory support (AD is LDAP-based; bundled AD preset)
- [ ] Secure transport: LDAPS + StartTLS
- [ ] Service-account bind for user lookup, then re-bind as the user to verify the password
- [ ] Configurable: host/port, bind DN + secret, base DN, user search filter, group search filter
- [ ] Attribute mapping (directory `mail` / `displayName` / `memberOf` → user profile + groups)
- [ ] Group → role mapping (directory groups to RBAC roles)
- [ ] JIT user provisioning on first successful bind
- [ ] Connection test / health check from admin UI
- [ ] Per-org connection (multi-tenant) and per-deployment connection (self-hosted) both supported
- [ ] Bind secret stored encrypted (envelope encryption, same KEK pattern as other secrets)

### SCIM (User Provisioning)

- [ ] SCIM 2.0 endpoint (`/scim/v2/Users`, `/scim/v2/Groups`)
- [ ] Bearer-token auth per endpoint
- [ ] Create / update / deactivate user
- [ ] Group → role mapping
- [ ] Deactivation revokes sessions + scopes keys
- [ ] SCIM provider abstraction (default + Okta + Entra presets)

### RBAC

- [ ] Built-in roles: `owner`, `admin`, `member`, `viewer`, `service`
- [ ] Permission catalog (one permission string per action across all modules)
- [ ] Permission check helper used by every module route
- [ ] Custom roles per org (combine permissions from catalog)
- [ ] Role assignment per actor (user or api key)
- [ ] Resource-scoped permissions (e.g., `kb:read` on specific KB)

### API Keys

- [ ] Personal keys (act-as-user, scoped to user permissions) — keys belong to the individual, not a team
- [ ] Service keys (act-as-service, attached to a custom role)
- [ ] Scoped keys (limited to specific modules / resources)
- [ ] Key prefix visible, secret shown once on creation
- [ ] Expiration date optional, max 1 year
- [ ] Last-used timestamp + IP
- [ ] Rotation: create new + revoke old, no downtime
- [ ] Key list + revoke per org
- [ ] Per-key rate limits (RPM / TPM / concurrent_requests) — set when minting/editing a key; enforced by the Gateway
- [ ] Per-key consumption governance — usage + spend tracked per key (i.e. per individual); feeds Gateway limits + budgets

### Audit Log

- [ ] Append-only `audit_events` table (no UPDATE, no DELETE except GDPR cascade)
- [ ] Every state-changing API call emits an event
- [ ] Event shape: `{id, org_id, actor, action, resource_type, resource_id, payload, ip, user_agent, ts}`
- [ ] Tamper-evidence: each event hashes prior event's id (Merkle chain)
- [ ] Search / filter by actor, resource, action, time range
- [ ] Export: CSV, JSONL, S3 destination
- [ ] Retention policy per org (default 7 years for compliance)
- [ ] Streaming export to SIEM (syslog, Splunk HEC, Datadog logs)

### Usage Metering

- [ ] `usage_events` table partitioned by month
- [ ] Standard units: `tokens_in`, `tokens_out`, `tokens_cache_read`, `tokens_cache_write`, `embeddings`, `documents_ingested`, `queries`, `worker_minutes`, `storage_gb`
- [ ] Per-event cost calculation at write time (frozen pricing snapshot)
- [ ] Rollups: hourly, daily, monthly
- [ ] Dashboard: per-user, per-team, per-key, per-model, per-module
- [ ] CSV / API export
- [ ] Webhook on usage threshold

### Quotas & Budgets

- [ ] Quota: hard cap per unit per period (e.g., `tokens_in <= 1M / day` for key X)
- [ ] Budget: $-denominated cap per org/team/user/key
- [ ] Soft warnings at 50% / 80% / 100% with notification
- [ ] Hard cutoff at 100% (deny further calls)
- [ ] Grace period (admin can extend, audited)
- [ ] Reset cadence (daily, monthly, custom)

### Billing

- [ ] Billing provider abstraction (`billing/protocol.py`)
- [ ] Bundled: Stripe (default), `manual` (invoice-only, no integration)
- [ ] Seat-based plan (per-user/month)
- [ ] Usage-based plan (overage on metered units)
- [ ] Hybrid plan (seat + usage)
- [ ] Invoice viewing, PDF download
- [ ] Payment method management (Stripe Elements)
- [ ] Plan upgrade / downgrade / cancel
- [ ] Free tier / trial / coupon support

### Webhooks (Outbound)

- [ ] Register webhook endpoint per org, scoped by event types
- [ ] Signed payloads (HMAC-SHA256, secret per endpoint)
- [ ] Retry with exponential backoff (max 24h)
- [ ] Delivery log + replay
- [ ] Event type catalog (each module declares its events)

### Notifications

- [ ] Channels: email (default), Slack, webhook, in-app
- [ ] Channel abstraction (`notify/protocol.py`)
- [ ] Bundled: SMTP, SES, SendGrid, Slack Incoming Webhook
- [ ] Per-user preference matrix (which events on which channels)
- [ ] Throttling / digesting

### Settings & Module Flags

- [ ] Org-level settings KV store
- [ ] Module-level enable/disable per org (`gateway`, `rag`, `memories`, `workers`)
- [ ] Feature-gate flags (e.g., `rag.search_providers.tavily=true`)
- [ ] Settings UI grouped by module

### Security

- [ ] MFA enrolment (TOTP) — required by org policy if set
- [ ] Session listing + revoke per user
- [ ] Login alerts (new device / new IP)
- [ ] Brute-force protection on login + key auth
- [ ] CSRF protection for cookie-auth routes
- [ ] Rate limit on auth endpoints
- [ ] Password strength requirements configurable per org

### Compliance / GDPR

- [ ] Data export request (Article 15): asynchronous job → S3 zip
- [ ] Data deletion request (Article 17): asynchronous job → cascade across modules
- [ ] Per-tenant data residency setting (single region v1, multi-region later)
- [ ] DPA / SCC document templates (links from settings UI)
- [ ] Encryption at rest on `audit_events` and `usage_events`

### Admin Console (in-app)

- [ ] Org overview (members, plan, usage summary)
- [ ] Members & roles
- [ ] Teams (members, per-team key count, team usage)
- [ ] SSO config
- [ ] Directory / LDAP config
- [ ] SCIM config
- [ ] API keys
- [ ] Webhooks
- [ ] Audit log viewer
- [ ] Usage dashboard
- [ ] Budgets & quotas
- [ ] Billing & invoices
- [ ] Settings (incl. module flags)
- [ ] Data export / delete

## Features — Out of Scope (for now)

- [ ] Multi-region active-active deployment
- [ ] BYOK (customer-managed encryption keys / KMS integration)
- [ ] ABAC beyond simple resource scoping (no policy DSL like Cedar/OPA)
- [ ] White-label / custom branding theming
- [ ] Self-service org sign-up at marketing scale (closed beta only for now)
- [ ] Localization beyond English (UI strings extracted but no translations shipped)
- [ ] Marketplace / app store
- [ ] Hardware security keys (WebAuthn / Passkeys) — TOTP only
- [ ] SCIM v1.1
- [ ] On-prem-only deployment guide (covered later in `self-hosted-deploy.md`)
- [ ] Custom audit-event types from external systems pushed in (only outbound for now)
- [ ] Kerberos / SPNEGO / Integrated Windows Auth (desktop SSO) — niche, deferred
- [ ] mTLS / client certificates / smart cards (PIV/CAC) — niche, deferred
- [ ] RADIUS authentication — niche, deferred
- [ ] Header / reverse-proxy delegated auth (oauth2-proxy, Pomerium, Cloudflare Access) — deferred

## Configurable Abstractions

### Identity Provider — enterprise SSO (`auth/idp/`)

- [ ] Interface: `IdentityProvider` with `initiate(state) -> redirect_url`, `complete(callback) -> UserClaims`
- [ ] Bundled: `saml`, `oidc`, `entra`, `okta`, `google`
- [ ] "How to add" doc with template

### Social Login Provider — consumer OAuth (`auth/social/`)

- [ ] Interface: `SocialProvider` with `authorize_url(state) -> url`, `exchange(callback) -> UserClaims`
- [ ] Bundled: `google`, `github`, `gitlab`
- [ ] Enabled per-deployment via auth config (independent of enterprise SSO)
- [ ] "How to add" doc with template

### Directory Provider — LDAP / AD (`auth/directory/`)

- [ ] Interface: `DirectoryProvider` with `authenticate(username, password) -> UserClaims`, `lookup(username) -> DirectoryEntry`, `test_connection() -> bool`
- [ ] Bundled: `ldap` (generic), `active_directory` preset
- [ ] Group → role mapping resolved from directory groups
- [ ] "How to add" doc with template

- [ ] Loads enabled strategies from YAML/env at boot (no `saas`/`selfhosted` mode flag)
- [ ] Declares: password on/off, social providers list, enterprise SSO availability
- [ ] Surfaced read-only to the frontend via the auth-config bootstrap endpoint

### SCIM Provider

- [ ] Interface compliant with RFC 7644
- [ ] Bundled: generic, `okta` preset, `entra` preset

### Billing Provider (`billing/`)

- [ ] Interface: `BillingProvider` with `create_customer`, `update_subscription`, `report_usage`, `void`
- [ ] Bundled: `stripe`, `manual` (no-op + invoice export)

### Notification Channel (`notify/channels/`)

- [ ] Interface: `Channel` with `send(recipient, template, payload)`
- [ ] Bundled: `smtp`, `ses`, `sendgrid`, `slack_webhook`, `in_app`

### Object Storage (`storage/`)

- [ ] Interface: `BlobStore` with `put`, `get`, `delete`, `presign_get`, `presign_put`
- [ ] Bundled: `s3`, `azure_blob`, `gcs`, `minio` (self-hosted), `local_fs` (dev only)

### Audit Sink

- [ ] Interface: `AuditSink` with `write(event)`, `query(filter)`
- [ ] Bundled: `postgres` (default), `s3_jsonl` (archive), `splunk_hec`, `datadog_logs`, `syslog`

## Data Model (sketch)

- [ ] `orgs(id, slug, name, region, status, created_at, deleted_at)`
- [ ] `users(id, email, password_hash, name, locale, mfa_required, created_at)`
- [ ] `org_members(org_id, user_id, role_id, joined_at)`
- [ ] `teams(id, org_id, slug, name, description, created_at, archived_at)`
- [ ] `team_members(team_id, user_id, role_id NULLABLE, joined_at)`
- [ ] `idp_connections(id, org_id, kind, config_json, enabled, sso_required)`
- [ ] `ldap_connections(id, org_id NULLABLE, host, port, bind_dn, bind_secret_enc, base_dn, user_filter, group_filter, tls_mode, attr_map_json, group_role_map_json, enabled)`
- [ ] `scim_endpoints(id, org_id, token_hash, last_sync_at)`
- [ ] `roles(id, org_id NULLABLE for system roles, name, description)`
- [ ] `permissions(id, key, description)` — seeded catalog
- [ ] `role_permissions(role_id, permission_id, resource_scope)`
- [ ] `api_keys(id, org_id, actor_user_id NULLABLE, name, prefix, hash, scopes_json, rate_limits_json, expires_at, last_used_at, revoked_at)` — owned by an individual; team attribution derived via `team_members`; `rate_limits_json` holds RPM/TPM/concurrency
- [ ] `audit_events(id, org_id, actor_json, action, resource_type, resource_id, payload_json, prev_hash, hash, ts)`
- [ ] `usage_events(id, org_id, actor_json, unit, quantity, cost_cents, resource_json, ts)` — partitioned monthly
- [ ] `quotas(id, org_id, scope_json, unit, period, limit, soft_warn_at)`
- [ ] `budgets(id, org_id, scope_json, period, limit_cents, soft_warn_at)`
- [ ] `webhooks(id, org_id, url, secret_hash, event_types_json, enabled)`
- [ ] `webhook_deliveries(id, webhook_id, event_id, status, attempts, last_response, next_attempt_at)`
- [ ] `org_settings(org_id, key, value_json)`
- [ ] `module_flags(org_id, module, enabled, gates_json)`
- [ ] `data_export_jobs(id, org_id, requested_by, status, result_url, requested_at, completed_at)`
- [ ] `data_delete_jobs(id, org_id, scope_json, status, requested_at, completed_at)`

## Public API (sketch)

- [ ] `GET /v1/auth/config` (public — enabled strategies + providers for the frontend)
- [ ] `POST /v1/auth/login` / `POST /v1/auth/sso/start` / `GET /v1/auth/sso/callback`
- [ ] `GET /v1/auth/social/{provider}/start` / `GET /v1/auth/social/{provider}/callback`
- [ ] `POST /v1/auth/ldap/login` (username + password → directory bind)
- [ ] `POST /v1/auth/logout` / `GET /v1/auth/me`
- [ ] `POST /v1/orgs` / `GET /v1/orgs/{id}` / `PATCH /v1/orgs/{id}`
- [ ] `GET /v1/orgs/{id}/members` / `POST /v1/orgs/{id}/invitations`
- [ ] `GET/POST /v1/orgs/{id}/teams` / `GET/PATCH/DELETE /v1/teams/{id}`
- [ ] `GET/POST/DELETE /v1/teams/{id}/members`
- [ ] `GET/POST/DELETE /v1/orgs/{id}/idp-connections`
- [ ] `GET/POST/DELETE /v1/orgs/{id}/ldap-connections` / `POST /v1/orgs/{id}/ldap-connections/{id}/test`
- [ ] `POST /scim/v2/Users` etc.
- [ ] `GET/POST/DELETE /v1/api-keys`
- [ ] `GET /v1/audit-events?...`
- [ ] `GET /v1/usage?...`
- [ ] `GET/POST /v1/quotas` / `GET/POST /v1/budgets`
- [ ] `GET/POST/DELETE /v1/webhooks`
- [ ] `GET/PATCH /v1/settings`
- [ ] `POST /v1/data-export` / `POST /v1/data-delete`

## UI Surface

- [ ] Login / signup / SSO redirect pages — adaptive: render only the strategies the deployment's auth-config enables (password / social buttons / SSO)
- [ ] Onboarding (create org, invite team)
- [ ] Admin → Members
- [ ] Admin → Teams (create team, assign members, per-team key count, team usage)
- [ ] Admin → SSO
- [ ] Admin → Directory / LDAP (connection config + test button)
- [ ] Admin → SCIM
- [ ] Admin → API Keys
- [ ] Admin → Audit Log (table + filters + export)
- [ ] Admin → Usage (charts + table)
- [ ] Admin → Budgets & Quotas
- [ ] Admin → Webhooks
- [ ] Admin → Billing
- [ ] Admin → Settings (incl. module toggles)
- [ ] Admin → Data Export / Delete
- [ ] User → Profile / MFA / Sessions

## Dependencies on Other Modules

- [ ] None

## Acceptance Criteria

- [ ] An org admin can sign up, configure SAML, invite users, assign roles, mint an API key, view audit log, set a budget, register a webhook, and disable a module — all via UI
- [ ] An org admin can create a team, assign users, and view per-team key counts + usage aggregated across the team's members (keys stay owned by individuals)
- [ ] A deployment declares its auth providers in config (YAML/env); the frontend login page renders only those strategies — no mode flag
- [ ] A user can sign in via Google / GitHub / GitLab social OAuth when that provider is enabled, including on a self-hosted deployment
- [ ] A user can authenticate via LDAP / Active Directory bind, and their directory groups map to RBAC roles on login
- [ ] Every other module's API rejects calls when the module is disabled for the calling org
- [ ] Every state-changing call writes an `audit_event` with the actor and prior-hash
- [ ] Every billable call writes a `usage_event` with cost
- [ ] GDPR delete on an org wipes all data across all modules within 24h
- [ ] SCIM creates / deactivates a user, role assignments respected on next login

## Testing

- [ ] Unit tests per file in `server/api/src/ai_portal/auth/`, `audit/`, `usage/`, `rbac/`, `billing/`
- [ ] Run only touched-file tests during implementation (`pytest path/to/file.py`)
- [ ] Defer E2E coverage to the post-implementation verification step
- [ ] E2E targets (added at the end): SSO login flow, social OAuth login flow, LDAP/AD bind login + group→role mapping, adaptive login renders configured strategies, invite + accept, create team + assign member, personal API key mint + use, per-team key count + usage aggregation, audit log filter + export, budget hard cutoff blocks gateway call
