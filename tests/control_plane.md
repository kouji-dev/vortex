# Control Plane — Manual Validation Checklist

Track what you've personally tested. Mark each item when verified by hand (UI or curl), with your own eyes.

Legend: `[ ]` not tested · `[~]` partial / flaky · `[x]` verified working · `[!]` broken (log in Notes)

Backend: `server/api/src/ai_portal/` · structured by **feature**, each provider/type tested separately.

---

# 1. Authentication

## 1.1 Local auth (password)
- [ ] Register / admin-create user with password
- [ ] Login email + password → access + refresh token issued
- [ ] Logout → token cleared, protected route redirects to /login
- [ ] Password change
- [ ] Password reset (forgot-password flow)
- [ ] Brute-force limiter — N bad logins → throttled / locked
- [ ] New-device login notification fires

## 1.2 MFA
- [ ] TOTP enroll (QR / secret shown)
- [ ] TOTP verify on login
- [ ] Login rejected with wrong / expired code
- [ ] Recovery / backup path (if present)

## 1.3 Sessions
- [ ] Session refresh — refresh_token mints new access_token
- [ ] Session list (active sessions visible)
- [ ] Session revoke — revoked session's token rejected
- [ ] Token expiry enforced

## 1.4 Request auth strategies (how an inbound request authenticates)
Files: `auth/strategies/`
- [ ] `jwt` — bearer JWT accepted, bad/expired JWT rejected
- [ ] `api_key` — API key strategy authenticates a request
- [ ] `portal_keys` — `sk_aip_…` portal key authenticates
- [ ] `entra` — Entra-issued token validated
- [ ] `dev` — dev strategy works in dev, **disabled in prod** (verify it can't auth in prod mode)

## 1.5 SSO / IdP — OIDC & SAML
Files: `auth/idp/providers/` — test each provider you intend to support.
- [ ] `oidc` (generic OIDC) — auth-code login → user provisioned
- [ ] `entra` (Azure AD) — login → claims mapped
- [ ] `okta` — login → claims mapped
- [ ] `google` (workspace IdP) — login
- [ ] `saml` — SP-initiated login → assertion consumed → session
- [ ] Claims → user provisioning (`claims_provision`) maps email/name/groups
- [ ] Group claim → role mapping (if configured)
- [ ] Unconfigured provider returns clean error (not 500)

## 1.6 Social login
Files: `auth/social/providers/`
- [ ] `github` — OAuth login → account linked
- [ ] `gitlab` — OAuth login
- [ ] `google` — OAuth login
- [ ] Account linking to existing email (no duplicate user)

## 1.7 Directory sync
Files: `auth/directory/providers/`
- [ ] `ldap` — bind + user search returns users
- [ ] `active_directory` — bind + sync
- [ ] Synced users appear in user list
- [ ] Secrets (`secret_box`) encrypted at rest, not echoed back

---

# 2. SCIM provisioning
Files: `scim/presets/` — test per IdP preset.
- [ ] `generic` preset — SCIM create user (external push)
- [ ] `okta` preset — create / update / deactivate user
- [ ] `entra` preset — create / update / deactivate user
- [ ] SCIM group → role / team mapping
- [ ] SCIM deactivate → user can no longer log in

---

# 3. RBAC
- [ ] Permission catalog loads (known permissions listed)
- [ ] Create / view role
- [ ] Assign role to user
- [ ] Remove role from user
- [ ] Permitted action → allowed
- [ ] Forbidden action → denied (403)
- [ ] Cross-org access denied (RLS isolation holds)
- [ ] Role change takes effect (document if re-login needed)

---

# 4. API keys
- [ ] Mint key → plaintext secret shown exactly once
- [ ] Minted key listed by prefix only (no secret)
- [ ] Key as bearer on gateway request → accepted
- [ ] Revoke key → subsequent use rejected (401)
- [ ] Key scoping / permission limits enforced (if applicable)
- [ ] Key expiry (if applicable)

---

# 5. Orgs, teams & module flags
- [ ] View current org
- [ ] Create team
- [ ] Add / remove team member
- [ ] Module flag toggles a module on/off per org
- [ ] Toggled-off module is actually inaccessible (deps guard returns 403/404)
- [ ] Multi-org: user in two orgs sees correct scope

---

# 6. Audit
- [ ] Action (e.g. `api_key.create`) produces an audit event
- [ ] Audit panel surfaces recent events
- [ ] Hash-chain integrity / immutability (tampered row detected)
- [ ] Filter by event type / actor / date
- [ ] Export audit log
- [ ] Sink delivery (at least Postgres; others: S3 / Splunk / Datadog / syslog if configured)

---

# 7. Settings
- [ ] View org / workspace settings
- [ ] Update a setting → persists across reload

---

# 8. Billing
- [ ] View plan / billing state
- [ ] Plan change reflected

---

# 9. Budgets
- [ ] Set a spend budget
- [ ] Over-limit request blocked / warned

---

# 10. Usage
- [ ] Usage metering records requests
- [ ] Usage panel shows consumption (tokens / cost)

---

# 11. GDPR
- [ ] Data-subject export
- [ ] Cascade delete removes user data across all modules

---

# 12. Retention
- [ ] Set retention window
- [ ] Sweeper deletes data past window

---

# 13. Webhooks
- [ ] Register outbound webhook
- [ ] Event fires → webhook delivered
- [ ] Delivery retry on failure

---

# 14. Notifications
- [ ] Notification sent (e.g. new-device login alert)

---

## Notes / broken items

<!-- Log [!] items: what broke, repro steps, file -->
