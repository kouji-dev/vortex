# Task 2 Report — Phase 2 Auth Rework

## Commits

- **a4f2b8f** — `refactor(auth): remove dev-bearer + entra branches from deps`
- **8e8078a** — `refactor(config): drop dev mode + auth_mode, default saas`

---

## Task 2.1 — deps.py

### Files changed
- `server/api/src/ai_portal/auth/deps.py`
- `server/api/src/ai_portal/auth/routes_rbac.py`
- `server/api/src/ai_portal/main.py`

### What was removed
- Imports: `decode_entra_access_token`, `roles_from_claims` (from `auth.strategies.entra`), `profile_fields_from_claims`, `upsert_user_from_entra_claims` (from `auth.service`)
- `_looks_like_compact_jws` helper (only used by entra block)
- Dev short-circuit block (~lines 75–91): `auth_mode == "dev"` fast path using `dev_bearer_token` + `dev_seed_user_email`
- Trailing dev block (~lines 120–134): duplicate `auth_mode == "dev"` fallback
- Entire `auth_mode == "entra"` block (~lines 136–175): Entra JWT decode/upsert
- Final `raise HTTPException("Unknown auth_mode")` fallthrough

### What was added
- Enterprise OIDC branch (before HS256 block): `deployment_mode == "selfhosted" and oidc_issuer` → RS256 detection → `authenticate_oidc_bearer`
- SaaS/selfhosted HS256 JWT block kept; now unconditional (no `if deployment_mode in (...)` guard needed since dev mode is gone)

### Extra references fixed
- `routes_rbac.py`: removed `auth_mode == "dev"` bypass in `require_app_roles`; removed `get_settings` import (no longer needed); updated docstring
- `main.py`: health endpoint replaced `st.auth_mode` with `st.deployment_mode`

---

## Task 2.2 — config.py

### Files changed
- `server/api/src/ai_portal/core/config.py`
- `server/api/.env.example`
- `server/api/tests/test_config_validation.py`

### What was removed from config.py
- `validate_portal_api_key_pepper_for_auth_mode` function (entire standalone function)
- YAML key map entries: `auth.mode`, `auth.dev_bearer_token`, `auth.dev_seed_user_email`
- Settings fields: `dev_bearer_token`, `dev_seed_user_email`, `auth_mode`
- `_entra_requires_portal_api_key_pepper` model_validator (called the deleted function)
- `settings_log_snapshot` keys: `auth_mode`, `dev_seed_user_email`, `dev_bearer_token_configured`
- Duplicate `deployment_mode` key in `settings_log_snapshot` (was listed twice after the refactor)

### deployment_mode change
- `Literal["dev", "saas", "selfhosted"]` → `Literal["saas", "selfhosted"]`
- Default: `"dev"` → `"saas"`

### .env.example changes
- Removed `AUTH_MODE=dev`, `DEV_BEARER_TOKEN=devtoken`, `DEV_SEED_USER_EMAIL=dev@localhost`
- Changed `DEPLOYMENT_MODE=dev` → `DEPLOYMENT_MODE=saas`
- Updated comments to reflect new two-mode system

### test_config_validation.py changes
- Removed: `test_validate_portal_api_key_pepper_entra_requires_non_empty`, `test_validate_portal_api_key_pepper_dev_allows_empty`, `test_settings_entra_rejects_blank_pepper`, `test_settings_entra_accepts_pepper`
- Added: `test_default_deployment_mode_is_saas`, `test_secret_key_required_for_saas`, `test_secret_key_required_for_selfhosted`, `test_saas_with_secret_key_ok`
- Updated YAML in `test_yaml_values_loaded_into_settings` and `test_env_var_overrides_yaml_secret`: removed `auth.mode`, `auth.dev_bearer_token`, `auth.dev_seed_user_email`; set `deployment_mode: saas`; added required `secret_key`

---

---

## Fix wave 1

Repairs dangling `dev`/`auth_mode` references identified in Phase 2 code review.

### Fix 1 — `server/api/src/ai_portal/main.py` CORS middleware
- Removed `deployment_mode == "dev"` conditional for `allow_origins` and `allow_credentials`.
- Now unconditional: `allow_origins=settings.cors_origin_list`, `allow_credentials=True`.

### Fix 2 — `server/api/src/ai_portal/auth/deps.py` HS256 path
- Wrapped `_uuid.UUID(payload["sub"])` in `try/except (KeyError, ValueError)`.
- Bad/missing `sub` now raises `HTTP 401 "Invalid token"` instead of HTTP 500.

### Fix 3 — `server/api/src/ai_portal/auth/routes_me.py` docstring
- `admin_ping` docstring rewrote: removed `auth_mode=entra (dev bypasses)` mention.
- Now reads: "RBAC probe: requires Admin app role. Returns 200 if caller holds the role, 403 otherwise."

### Fix 4 — `server/api/.env.example` comment
- Changed "Required HMAC pepper when AUTH_MODE=entra" → "Required HMAC pepper for portal API keys".

### Fix 5 — `server/api/tests/test_health.py`
- `assert data["auth_mode"] == "dev"` → `assert data["deployment_mode"] == "saas"`.

### Fix 6 — `server/api/tests/test_portal_api_keys.py`
- Removed `Bearer devtoken` and `get_settings().dev_seed_user_email` references (both deleted in Phase 2).
- Rewrote: creates `Org` + `User` via `db_session` fixture, mints a real SaaS JWT via `create_access_token(user_uuid, org_id, role, secret)`, asserts `me.json()["email"] == user.email`.
- Added `pytestmark = requires_postgres` (test now requires DB).

### Fix 7 — Smoke tests
- **`test_smoke_control_plane.py`**: removed `AUTH_MODE=dev` from the docstring boot command.
- **`test_smoke_memory.py`**: updated docstring run command (`DEPLOYMENT_MODE=saas SECRET_KEY=...` instead of `AUTH_MODE=dev DEPLOYMENT_MODE=dev`). Added `# TODO(auth-rework): smoke auth needs real JWT` comment before `HDR = {"Authorization": "Bearer devtoken"}`.
- **`test_smoke_rag.py`**: updated docstring run command; updated `_smoke_env` fixture — dropped `AUTH_MODE` from prior/restore dict and from `os.environ.setdefault` calls, changed `DEPLOYMENT_MODE` default to `"saas"`, added `SECRET_KEY` default.
- **`test_smoke_workers.py`**: updated `_REQUIRED_ENV` (dropped `AUTH_MODE=dev`, changed `DEPLOYMENT_MODE` check to accept `saas`/`selfhosted` + require `SECRET_KEY`), updated `requires_env` skip reason. Added `# TODO(auth-rework): smoke auth needs real JWT` comment before `_auth_headers()` return.

### Smoke tests with deeper dev-bearer auth dependency (TODO-marked)

These tests make HTTP calls using `Bearer devtoken` which no longer authenticates after Phase 2. The boot/config env was fixed (Settings won't crash), but the authenticated call sites still carry the old token and will get HTTP 401 at runtime:

- **`test_smoke_memory.py`** — `HDR = {"Authorization": "Bearer devtoken"}` used in all `/v1/memories` calls in `test_smoke_golden_path` and `test_smoke_byok_encryption`. Also accesses DB for `dev@localhost` user which may not exist.
- **`test_smoke_workers.py`** — `_auth_headers()` returns `Bearer devtoken`; used in `test_health_then_auth`, `test_create_pool_then_submit_task`, `test_task_walks_lifecycle_via_service`, `test_sse_endpoint_authorised_and_serves_backfill`. Also queries `User.email == "dev@localhost"` in `test_request_trace_correlation_by_task_id`.

Both are marked with `# TODO(auth-rework): smoke auth needs real JWT` at the call site.

Tests not run per user instruction.

---

## Concerns

- `entra_tenant_id`, `entra_api_audience`, `entra_debug_jwt` fields remain in config.py. They are referenced by nothing in the active auth path (the entra block was deleted), but kept to avoid breaking any external config that sets these. Can be removed in a follow-up cleanup if desired.
- `routes_me.py` line 48 has a stale docstring ("requires Entra app role Admin when auth_mode=entra (dev bypasses)") — cosmetic only, not a functional issue. Updated in routes_rbac.py.
- `test_control_plane_deps.py` did not require changes — its tests use `dependency_overrides` to bypass `_authenticate` entirely, so no dev-token assertions existed there.
