# SSO (SAML + Entra)

## 1. Purpose
One IdP login for all gateway users. Generic SAML 2.0 + keep existing Entra path. No local passwords in prod.

## 2. Buyer pain (CISO/RSSI + IT)
- Banks mandate SSO + MFA via corporate IdP (Entra, Ping, Okta, ADFS). No exceptions.
- Joiner-mover-leaver: IT needs offboarding to kill gateway access within minutes, audited.
- Today: ChatGPT Enterprise = Entra-only or pay extra. SG/BNP run hybrid ADFS + Entra; need generic SAML.

## 3. Sub-features
- Generic SAML 2.0 SP, per-org IdP metadata upload [must-have] (banks mandate, no SaaS without it)
- Entra OIDC reuse via `strategies/entra.py` [must-have] (existing code, zero cost)
- JIT user creation on first login [must-have] (no manual onboarding)
- Group-to-role mapping configurable per org [must-have] (every bank uses different AD group naming — `gw-admins` vs `GRP_AI_ADMIN` vs `CN=AI_Ops`)
- JIT group sync on every login [must-have] (revokes role within one session of IdP group change — covers mover; leaver covered by IdP killing login)
- SCIM 2.0 provisioning [must-have] (DORA joiner-mover-leaver needs sub-hour deprovisioning + audit trail; JIT alone fails for stale sessions and dormant accounts)
- MFA pass-through, trust IdP `amr`/`AuthnContext` [must-have] (bank policy)
- SP-initiated + IdP-initiated login [must-have] (IdP-init = bank portal tile)
- SLO via SAML LogoutRequest [must-have] (kill gateway on IdP logout)
- Signed AuthnRequest + encrypted assertions [must-have] (security review gate)
- Per-org IdP config UI [must-have] (self-serve onboarding, cuts our integration time)
- Okta/Ping/ADFS tested presets [nice-to-have] (speeds POCs, not blocking)
- Social login Google/GitHub [skip] (banks ban it)
- Custom attribute mapper DSL [skip] (YAGNI, JSON map covers 95%)

## 4. Tasks
1. Add `python3-saml` (or `pysaml2`) to `server/api/pyproject.toml`.
2. New `server/api/src/ai_portal/auth/strategies/saml.py`: ACS handler, metadata parser, assertion validator, signature/encryption.
3. New table `org_idp_config` (org_id, type=`saml|oidc`, metadata_xml, entity_id, acs_url, cert, group_attr, role_map JSONB) — Alembic in `server/api/alembic/versions/`.
4. Routes in `server/api/src/ai_portal/auth/router.py`: `GET /sso/{org_slug}/metadata`, `POST /sso/{org_slug}/acs`, `GET /sso/{org_slug}/login`, `POST /sso/{org_slug}/slo`.
5. Refactor `auth/service.py`: extract `resolve_or_create_user(email, org, attrs)` for JIT, called by both Entra and SAML strategies.
6. Group mapping helper `auth/group_mapper.py`: SAML `groups` claim -> role via `role_map` JSON; idempotent per login.
7. Extend `auth/model.py` `User`: `external_id`, `idp_type`, `last_idp_sync_at`.
8. Admin UI `apps/frontend/src/components/admin/SsoConfigPage.tsx`: upload IdP XML, set group->role map, copy SP metadata URL.
9. Login page: org slug input -> redirect to SP-init SAML or Entra.
10. E2E `apps/frontend/e2e/sso-saml.spec.ts`: mock IdP via `samltest.id` or stubbed ACS POST, assert JIT user + role.

## 5. Competitive note
Portkey: SSO is enterprise add-on, Okta/Entra only, no generic SAML. LiteLLM Enterprise: SSO yes, group mapping weak. Cloudflare AI Gateway: no per-tenant SSO. Per-org SAML + group->role JSON is table-stakes for banks and our entry ticket.

## 6. Risks
- SAML XML signature wrapping; use vetted lib, never hand-parse.
- Clock skew breaks assertions; enforce NTP, allow 3min drift.
- Per-org cert rotation; surface expiry in admin UI, alert 30d out.
- IdP-init CSRF; require RelayState validation.
- Bank Entra quirks (custom claims, conditional access, named-location blocks) break first integration; budget 1wk debug per design partner, capture claim dumps in admin UI.
- SAML IdP setup = 1-2wk per customer (their IT, not ours) = sales-cycle drag; ship self-serve metadata + presets to compress to days.
- MFA pass-through breaks if IdP changes step-up rules mid-session; treat missing `amr` as re-auth required, not as failure.

## 7. Done-when
Demo: upload Okta/ADFS metadata for `acme-bank` org, login from IdP tile, JIT user lands with `admin` role from `gw-admins` group, logout kills both sessions.
