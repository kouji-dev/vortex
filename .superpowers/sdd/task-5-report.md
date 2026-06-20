# Phase 5 Auth Cleanup — Report

## Summary

All 7 tasks completed. Import checks passed after each task. Grep verify for dropped schema refs: empty.

---

## Task 5.1 — chore(auth): remove Entra/MSAL backend
**Commit:** `014509f`

**Files deleted:**
- `auth/strategies/entra.py`
- `auth/idp/providers/entra.py`
- `auth/strategies/api_key.py` (initially deleted, then restored — see Deviations)
- `auth/service.py` (entire file — only contained Entra helpers)
- `tests/test_auth_entra.py`

**References updated:**
- `auth/__init__.py` — removed `decode_entra_access_token`, `roles_from_claims` re-exports
- `auth/idp/providers/__init__.py` — removed `entra` side-effect import
- `core/config.py` — removed `entra_tenant_id`, `entra_api_audience`, `entra_debug_jwt` fields + log snapshot refs

**Import check:** PASS

**Note:** `routes_me.py` and `routes_rbac.py` had no Entra refs — nothing to update.

---

## Task 5.2 — chore(auth): remove SAML/Okta/dev strategies
**Commit:** `2e3dbce`

**Files deleted:**
- `auth/idp/providers/saml.py`
- `auth/idp/providers/okta.py`

**References updated:**
- `auth/idp/providers/__init__.py` — removed `okta`, `saml` side-effect imports
- `auth/routes_sso.py` — removed `sso_callback_post` (SAML form-post callback)

**Deviation:** `auth/strategies/dev.py` NOT deleted (see Deviations).

**Import check:** PASS

---

## Task 5.3 — chore(auth): remove LDAP/AD directory
**Commit:** `6e945f1`

**Files deleted:**
- `auth/directory/` (entire package: `__init__.py`, `model.py`, `protocol.py`, `registry.py`, `schemas.py`, `secret_box.py`, `service.py`, `providers/__init__.py`, `providers/active_directory.py`, `providers/ldap.py`)
- `auth/routes_ldap.py`
- `tests/auth/directory/__init__.py`
- `tests/auth/directory/test_ldap_provider.py`

**References updated:**
- `main.py` — removed `auth_ldap_admin_router` and `auth_ldap_public_router` imports + `app.include_router` calls

No LDAP env vars existed in `.env.example`.

**Import check:** PASS

---

## Task 5.4 — chore(auth): remove SCIM
**Commit:** `c62dabb`

**Files deleted:**
- `scim/` (entire package: `__init__.py`, `model.py`, `router.py`, `schemas.py`, `service.py`, `presets/__init__.py`, `presets/base.py`, `presets/entra.py`, `presets/generic.py`, `presets/okta.py`)
- `tests/scim/__init__.py`
- `tests/scim/test_presets.py`
- `tests/scim/test_scim_users.py`

**References updated:**
- `main.py` — removed `scim_admin_router`, `scim_router` imports + includes; removed `/api/scim/` → `/scim/` path-rewrite middleware
- `rag/acl/permission_test.py` — removed `ScimGroupMember` import; `_load_user_group_ids` now returns `[]`
- `rag/acl/idp_mapping.py` — removed `ScimGroup` import; `resolve_group` now returns `None`; removed `User.entra_object_id` lookup from `resolve_user`
- `knowledge_base/schemas.py` — updated stale comment referencing `scim_group_members`

No SCIM env vars existed in `.env.example`.

**Import check:** PASS

---

## Task 5.5 — chore(auth): remove MFA/setup/gitlab
**Commit:** `0173ddd`

**Files deleted:**
- `auth/mfa_totp.py`
- `auth/routes_mfa.py`
- `auth/routes_setup.py`
- `auth/social/providers/gitlab.py`
- `tests/test_mfa_totp.py`

**References updated:**
- `main.py` — removed `auth_mfa_router` + `setup_router` imports + includes
- `auth/router.py` — removed `mfa_totp` imports + MFA gate in login endpoint
- `auth/schemas.py` — removed `TotpEnrollResponse`, `TotpVerifyRequest`; removed `totp_code` field from `LoginRequest`
- `auth/social/providers/__init__.py` — removed `gitlab` side-effect import

**Import check:** PASS

---

## Task 5.6 — chore(auth): prune dead auth env + confirm surface
**Commit:** `aee6a4e`

**Changes:**
- `.env.example` — removed `ENTRA_TENANT_ID`, `ENTRA_API_AUDIENCE`, `ENTRA_DEBUG_JWT`

**Final auth/ surface (non-pycache .py files):**
- `oidc/` (bearer, jwks, provisioning, role_map) — KEPT per brief
- `idp/providers/{oidc.py, google.py}` — KEPT per brief
- `idp/{protocol.py, registry.py, model.py}` — KEPT per brief
- `strategies/{jwt.py, portal_keys.py}` — KEPT per brief
- `strategies/api_key.py` — KEPT (deviation, see below)
- `strategies/dev.py` — KEPT (deviation, see below)
- `social/providers/{github.py, google.py, _base.py}` — KEPT per brief
- `{password,sessions,deps,router,model}.py` — KEPT per brief
- `routes_{sso,members,orgs,me,social,rbac,auth_config,control_plane}.py` — KEPT per brief
- Supporting: `claims_provision.py`, `config/`, `limiter.py`, `repository.py`, `schemas.py`, `sso.py`, `orgs_*.py`, `users_*.py`, `new_device_notify.py`

---

## Task 5.7 — chore(db): drop legacy scim/ldap/mfa/entra schema (migration 075)
**Commit:** `6393c68`

**Files created:**
- `alembic/versions/075_drop_legacy_auth_schema.py` (down_revision="074", exact spec from brief)

**Model changes:**
- `auth/model.py` — removed `UserMfaFactor` class; removed `entra_object_id`, `scim_external_id`, `mfa_required` columns from `User`

**Additional fixes required:**
- `auth/users_schemas.py` — removed `mfa_required` from `UserProfileOut`
- `auth/routes_control_plane.py` — removed `mfa_required=u.mfa_required` from `_profile_out()`

**Grep verify:**
```
grep -rn "user_mfa_factors\|scim_\|ldap_connections\|entra_object_id\|scim_external_id\|mfa_required" server/api/src --include="*.py" | grep -v __pycache__
→ empty (PASS)
```

**Import check:** PASS

---

## Deviations from Brief

### `auth/strategies/api_key.py` — KEPT (brief said delete)
**Reason:** `control_plane/deps.py` imports `actor_for_api_key_token` and `looks_like_api_key_token` from this file. This strategy authenticates control-plane API keys (`ap_xxx` prefix) — a kept feature used by every admin API route. Deleting it would break all API key auth. The file was initially deleted but immediately restored after the import check failed.

### `auth/strategies/dev.py` — KEPT (brief said delete as "dev strategy")
**Reason:** `router.py` (KEPT), `routes_sso.py` (KEPT), and `routes_social.py` (KEPT) all import `UserManager`, `RegistrationError`, and `AuthenticationError` from this file. `UserManager` is the production password-auth + token-minting service — not a dev-only stub. Deleting it would break login, register, refresh, SSO callbacks, and social login. The name "dev strategy" was misleading; the class is production code.

---

## Concerns

1. **`auth/strategies/dev.py` naming**: Should be renamed to something like `auth/strategies/local.py` or `auth/user_manager.py` in a follow-up to avoid confusion.

2. **`auth/strategies/api_key.py`**: Should probably live in `api_keys/` rather than `auth/strategies/` since it's not a user-auth strategy — it's an API-key resolution helper.

3. **Group resolution dead**: `rag/acl/idp_mapping.py#resolve_group` and `rag/acl/permission_test.py#_load_user_group_ids` now return `None`/`[]` respectively. KB ACL group-based filtering is broken until a replacement group-membership mechanism is wired. Track as a follow-up.

4. **Migration 075 not run**: As instructed, alembic was NOT executed. Must be run as part of the final deployment pass.

5. **`rbac/catalog.py`** still lists `scim:read` and `scim:write` permissions (lines 53-54). These are now orphaned permission strings but harmless. Can be cleaned up in a follow-up RBAC catalog pruning task.
