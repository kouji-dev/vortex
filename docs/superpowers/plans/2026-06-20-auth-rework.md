# Auth Rework — SaaS + Enterprise Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework auth so the app is a pure OIDC consumer that owns orgs/invites/RBAC, runs as SaaS (own IdP: password + GitHub/Google) or enterprise (customer's Keycloak), and deletes all off-path legacy auth.

**Architecture:** One unified auth dependency. Core verifies any IdP token → maps groups → JIT-provisions → attaches RBAC role. SaaS mode issues its own HS256 JWT via Authlib; enterprise validates a customer's RS256 token via JWKS. Everything else (Entra/MSAL/SAML/Okta/LDAP/SCIM/MFA, dev-bearer) is removed.

**Tech Stack:** FastAPI, SQLAlchemy, PyJWT (`PyJWKClient`), Authlib, pytest, Playwright, Keycloak (test IdP).

## Global Constraints

- Spec: `docs/pivot/2026-06-20-auth-plan.md`. This plan implements all of §A–§H.
- Deployment modes after this plan: `deployment_mode: Literal["saas", "selfhosted"]`, **default `"saas"`**. `dev` mode and `auth_mode` are **removed**. Local dev runs full SaaS login.
- User model is **single-org**: `User.org_id: UUID | None`, `User.role: str`. No membership join table. `OrgInvite` model already exists (`auth/model.py`).
- Internal RBAC roles: `owner`, `admin`, `member`, `viewer`.
- `UserClaims` (`auth/idp/protocol.py`): `subject`, `email`, `name`, `groups`, `raw`.
- Chat-types sync rule and E2E-DB isolation (port 8001 / `ai_portal_e2e`) from `CLAUDE.md` still apply.
- TDD for new logic. Deletions: remove → grep proves no live imports → suite green → commit. Commit after every task.
- DB tests need `DATABASE_URL`; a skip is NOT a pass.

---

## Phase 1 — Auth core (OIDC consumer)

### Task 1.1: Group → role mapping

**Files:**
- Create: `server/api/src/ai_portal/auth/oidc/__init__.py` (empty)
- Create: `server/api/src/ai_portal/auth/oidc/role_map.py`
- Test: `server/api/tests/test_oidc_role_map.py`

**Interfaces:**
- Produces: `map_groups_to_role(groups: Sequence[str], mapping: dict[str, str], default: str = "member") -> str`. Priority `owner > admin > member > viewer`.

- [ ] **Step 1: Failing test**

```python
# server/api/tests/test_oidc_role_map.py
from ai_portal.auth.oidc.role_map import map_groups_to_role
MAP = {"IT-Admins": "admin", "Owners": "owner", "Engineering": "member"}

def test_maps_matched_group():
    assert map_groups_to_role(["Engineering"], MAP) == "member"

def test_unmatched_fall_back_to_default():
    assert map_groups_to_role(["Finance"], MAP, default="viewer") == "viewer"
    assert map_groups_to_role([], MAP) == "member"

def test_highest_priority_wins():
    assert map_groups_to_role(["Engineering", "Owners"], MAP) == "owner"

def test_unknown_target_role_ignored():
    assert map_groups_to_role(["X"], {"X": "sysadmin"}, default="member") == "member"
```

- [ ] **Step 2: Verify fail** — `cd server/api && python -m pytest tests/test_oidc_role_map.py -v` → `ModuleNotFoundError`
- [ ] **Step 3: Implement**

```python
# server/api/src/ai_portal/auth/oidc/role_map.py
from __future__ import annotations
from collections.abc import Sequence

_ROLE_PRIORITY = ("owner", "admin", "member", "viewer")

def map_groups_to_role(groups: Sequence[str], mapping: dict[str, str], default: str = "member") -> str:
    matched = [mapping[g] for g in groups if g in mapping and mapping[g] in _ROLE_PRIORITY]
    return min(matched, key=_ROLE_PRIORITY.index) if matched else default
```

- [ ] **Step 4: Verify pass** — same pytest → 4 passed
- [ ] **Step 5: Commit** — `git add server/api/src/ai_portal/auth/oidc/ server/api/tests/test_oidc_role_map.py && git commit -m "feat(auth): group-to-role mapping"`

### Task 1.2: JWKS signature verification

**Files:**
- Create: `server/api/src/ai_portal/auth/oidc/jwks.py`
- Test: `server/api/tests/test_oidc_jwks.py`

**Interfaces:**
- Produces: `verify_id_token(token, *, jwks_uri, issuer, audience, leeway=30) -> dict` (raises `jwt.PyJWTError`); `make_claims(payload: dict) -> UserClaims`.
- **Why:** `auth/idp/providers/oidc.py:_claims_from_token` decodes id_tokens WITHOUT signature check (`# MVP: trust the IdP`). Unsafe — this replaces it (wired in Task 4.x).

- [ ] **Step 1: Failing test**

```python
# server/api/tests/test_oidc_jwks.py
import json, jwt, pytest, respx
from cryptography.hazmat.primitives.asymmetric import rsa
from ai_portal.auth.oidc.jwks import verify_id_token, make_claims

@pytest.fixture
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)

def _jwks(key, kid="k1"):
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())); jwk["kid"] = kid
    return {"keys": [jwk]}

@respx.mock
def test_verifies_valid_token(rsa_key):
    respx.get("https://idp.test/jwks").respond(json=_jwks(rsa_key))
    tok = jwt.encode({"sub":"u1","email":"a@b.c","iss":"https://idp.test","aud":"vortex-app"}, rsa_key, algorithm="RS256", headers={"kid":"k1"})
    assert verify_id_token(tok, jwks_uri="https://idp.test/jwks", issuer="https://idp.test", audience="vortex-app")["sub"] == "u1"

@respx.mock
def test_rejects_wrong_audience(rsa_key):
    respx.get("https://idp.test/jwks").respond(json=_jwks(rsa_key))
    tok = jwt.encode({"sub":"u1","email":"a@b.c","iss":"https://idp.test","aud":"other"}, rsa_key, algorithm="RS256", headers={"kid":"k1"})
    with pytest.raises(jwt.InvalidAudienceError):
        verify_id_token(tok, jwks_uri="https://idp.test/jwks", issuer="https://idp.test", audience="vortex-app")

def test_make_claims_groups():
    uc = make_claims({"sub":"u1","email":"a@b.c","groups":["Eng"]})
    assert uc.subject=="u1" and uc.groups==("Eng",)
```

- [ ] **Step 2: Verify fail** — `python -m pytest tests/test_oidc_jwks.py -v` → ModuleNotFoundError
- [ ] **Step 3: Implement**

```python
# server/api/src/ai_portal/auth/oidc/jwks.py
from __future__ import annotations
import jwt
from jwt import PyJWKClient
from ai_portal.auth.idp.protocol import UserClaims

_clients: dict[str, PyJWKClient] = {}

def _client(uri: str) -> PyJWKClient:
    c = _clients.get(uri)
    if c is None:
        c = PyJWKClient(uri, cache_keys=True); _clients[uri] = c
    return c

def verify_id_token(token: str, *, jwks_uri: str, issuer: str, audience: str, leeway: int = 30) -> dict:
    key = _client(jwks_uri).get_signing_key_from_jwt(token)
    return jwt.decode(token, key.key, algorithms=["RS256"], audience=audience, issuer=issuer,
                      leeway=leeway, options={"require": ["exp", "iat", "sub"]})

def make_claims(payload: dict) -> UserClaims:
    sub, email = payload.get("sub"), payload.get("email")
    if not sub or not email:
        raise jwt.InvalidTokenError("token missing 'sub' or 'email'")
    g = payload.get("groups") or ()
    groups = tuple(g) if isinstance(g, (list, tuple)) else ()
    return UserClaims(subject=str(sub), email=str(email), name=payload.get("name"), groups=groups, raw=payload)
```

- [ ] **Step 4: Verify pass** — 3 passed
- [ ] **Step 5: Commit** — `git commit -am "feat(auth): JWKS signature verification"`

### Task 1.3: JIT provisioning

**Files:**
- Create: `server/api/src/ai_portal/auth/oidc/provisioning.py`
- Modify: `server/api/tests/conftest.py` (add `db_session`, `org`, `rsa_key` fixtures)
- Test: `server/api/tests/test_oidc_provisioning.py`

**Interfaces:**
- Produces: `jit_provision(db: Session, *, claims: UserClaims, org_id: uuid.UUID, role: str) -> User` — idempotent find-by-email, create-if-absent, set org+role+active.

- [ ] **Step 1: Add fixtures to `conftest.py`**

```python
import pytest, uuid as _uuid
from sqlalchemy.orm import Session
from ai_portal.core.db.session import SessionLocal

@pytest.fixture
def db_session():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.rollback(); db.close()

@pytest.fixture
def org(db_session):
    from ai_portal.auth.model import Org
    o = Org(slug=f"acme-{_uuid.uuid4().hex[:8]}", name="Acme")
    db_session.add(o); db_session.flush(); return o

@pytest.fixture
def rsa_key():
    from cryptography.hazmat.primitives.asymmetric import rsa
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)
```

- [ ] **Step 2: Failing test**

```python
# server/api/tests/test_oidc_provisioning.py
import uuid, pytest
from sqlalchemy import select
from ai_portal.auth.idp.protocol import UserClaims
from ai_portal.auth.model import User
from ai_portal.auth.oidc.provisioning import jit_provision
from tests.conftest import requires_postgres
pytestmark = requires_postgres

def test_creates_user_first_login(db_session, org):
    u = jit_provision(db_session, claims=UserClaims(subject="kc|1", email="new@acme.test", name="New"), org_id=org.id, role="member")
    assert u.id and u.org_id == org.id and u.role == "member" and u.is_active

def test_idempotent_updates_role(db_session, org):
    c = UserClaims(subject="kc|2", email="dup@acme.test", name="Dup")
    a = jit_provision(db_session, claims=c, org_id=org.id, role="member")
    b = jit_provision(db_session, claims=c, org_id=org.id, role="admin")
    assert a.id == b.id and b.role == "admin"
    assert len(db_session.scalars(select(User).where(User.email == "dup@acme.test")).all()) == 1
```

- [ ] **Step 3: Verify fail** — `DATABASE_URL=$E2E_DATABASE_URL python -m pytest tests/test_oidc_provisioning.py -v` → ModuleNotFoundError
- [ ] **Step 4: Implement**

```python
# server/api/src/ai_portal/auth/oidc/provisioning.py
from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from ai_portal.auth.idp.protocol import UserClaims
from ai_portal.auth.model import User

def jit_provision(db: Session, *, claims: UserClaims, org_id: uuid.UUID, role: str) -> User:
    user = db.scalars(select(User).where(User.email == claims.email)).first()
    if user is None:
        user = User(uuid=uuid.uuid4(), email=claims.email, name=claims.name,
                    org_id=org_id, role=role, is_active=True, is_verified=True)
        db.add(user)
    else:
        user.org_id, user.role, user.is_active = org_id, role, True
    db.flush(); return user
```

- [ ] **Step 5: Verify pass** — 2 passed
- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat(auth): JIT provisioning from claims"`

### Task 1.4: Enterprise OIDC bearer + settings

**Files:**
- Create: `server/api/src/ai_portal/auth/oidc/bearer.py`
- Modify: `server/api/src/ai_portal/core/config.py` (add OIDC settings)
- Test: `server/api/tests/test_oidc_bearer_auth.py`

**Interfaces:**
- Produces: `authenticate_oidc_bearer(db, token, settings) -> tuple[User, str]`. Reads `settings.oidc_issuer/oidc_jwks_uri/oidc_client_id/oidc_group_role_map/oidc_default_org_id`.

- [ ] **Step 1: Failing test**

```python
# server/api/tests/test_oidc_bearer_auth.py
import json, jwt
from ai_portal.auth.oidc.bearer import authenticate_oidc_bearer
from tests.conftest import requires_postgres
import respx
pytestmark = requires_postgres

class _S:
    oidc_issuer="https://idp.test"; oidc_jwks_uri="https://idp.test/jwks"
    oidc_client_id="vortex-app"; oidc_group_role_map={"IT-Admins":"admin"}

@respx.mock
def test_valid_token_provisions_and_maps(db_session, org, rsa_key):
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(rsa_key.public_key())); jwk["kid"]="k1"
    respx.get("https://idp.test/jwks").respond(json={"keys":[jwk]})
    tok = jwt.encode({"sub":"kc|9","email":"alice@acme.test","groups":["IT-Admins"],
                      "iss":"https://idp.test","aud":"vortex-app"}, rsa_key, algorithm="RS256", headers={"kid":"k1"})
    s = _S(); s.oidc_default_org_id = org.id
    user, role = authenticate_oidc_bearer(db_session, tok, s)
    assert user.email == "alice@acme.test" and role == "admin"
```

- [ ] **Step 2: Verify fail** — ModuleNotFoundError
- [ ] **Step 3: Implement bearer**

```python
# server/api/src/ai_portal/auth/oidc/bearer.py
from __future__ import annotations
import jwt
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from ai_portal.auth.oidc.jwks import verify_id_token, make_claims
from ai_portal.auth.oidc.role_map import map_groups_to_role
from ai_portal.auth.oidc.provisioning import jit_provision
from ai_portal.auth.model import User

def authenticate_oidc_bearer(db: Session, token: str, settings) -> tuple[User, str]:
    try:
        payload = verify_id_token(token, jwks_uri=settings.oidc_jwks_uri,
                                  issuer=settings.oidc_issuer, audience=settings.oidc_client_id)
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid IdP token") from e
    claims = make_claims(payload)
    role = map_groups_to_role(claims.groups, settings.oidc_group_role_map or {})
    user = jit_provision(db, claims=claims, org_id=settings.oidc_default_org_id, role=role)
    return user, role
```

- [ ] **Step 4: Add settings** to `core/config.py` near `deployment_mode`:

```python
    oidc_issuer: str = Field(default="", validation_alias=AliasChoices("OIDC_ISSUER"))
    oidc_jwks_uri: str = Field(default="", validation_alias=AliasChoices("OIDC_JWKS_URI"))
    oidc_client_id: str = Field(default="", validation_alias=AliasChoices("OIDC_CLIENT_ID"))
    oidc_default_org_id: uuid.UUID | None = Field(default=None, validation_alias=AliasChoices("OIDC_DEFAULT_ORG_ID"))
    oidc_group_role_map: dict[str, str] = Field(default_factory=dict)
```

- [ ] **Step 5: Verify pass** — `DATABASE_URL=$E2E_DATABASE_URL python -m pytest tests/test_oidc_*.py -v` → all pass
- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat(auth): enterprise OIDC bearer authentication"`

---

## Phase 2 — Remove dev auth, default to SaaS

Removes the dev-bearer short-circuit and `auth_mode`. Local dev = full SaaS login. Enterprise OIDC wired into the dependency here.

### Task 2.1: Strip dev/entra branches from the auth dependency

**Files:**
- Modify: `server/api/src/ai_portal/auth/deps.py`
- Test: `server/api/tests/test_control_plane_deps.py` (update expectations)

- [ ] **Step 1:** In `deps.py` `_authenticate`, delete: the dev short-circuit (`auth_mode == "dev"` block, ~75-91), the trailing `auth_mode == "dev"` block (~120-134), and the entire `auth_mode == "entra"` block (~136-175). Remove imports of `decode_entra_access_token`, `roles_from_claims`, `upsert_user_from_entra_claims`, `profile_fields_from_claims`.
- [ ] **Step 2:** Replace the deployment-mode block with SaaS-JWT + enterprise-OIDC:

```python
    if settings.deployment_mode == "selfhosted" and settings.oidc_issuer:
        if token.count(".") == 2 and jwt.get_unverified_header(token).get("alg", "").startswith("RS"):
            from ai_portal.auth.oidc.bearer import authenticate_oidc_bearer
            user, role = authenticate_oidc_bearer(db, token, settings)
            request.state.app_roles = [role]
            return user

    # SaaS / selfhosted local JWT (HS256, our own IdP)
    try:
        payload = decode_token(token, secret=settings.secret_key)
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from e
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not an access token")
    # ... (keep existing uuid lookup + session-active check unchanged) ...
```

- [ ] **Step 3:** Run `DATABASE_URL=$E2E_DATABASE_URL python -m pytest tests/test_control_plane_deps.py -v`; fix any dev-token assertions to use a real SaaS JWT (`create_access_token`). Expected: PASS.
- [ ] **Step 4: Commit** — `git commit -am "refactor(auth): remove dev-bearer + entra branches from deps"`

### Task 2.2: Drop `dev` mode + `auth_mode` from config

**Files:**
- Modify: `server/api/src/ai_portal/core/config.py`
- Modify: `server/api/.env.example`
- Test: `server/api/tests/test_config_validation.py`

- [ ] **Step 1:** Change `deployment_mode: Literal["dev", "saas", "selfhosted"]` → `Literal["saas", "selfhosted"]`, default `"saas"`. Delete `auth_mode` field, `dev_bearer_token`, `dev_seed_user_email`, and `validate_portal_api_key_pepper_for_auth_mode` (and its call). Remove `auth_mode`/`dev_*` from the settings dict exports (~line 373) and `.env.example`.
- [ ] **Step 2:** Update `test_config_validation.py` — remove dev/auth_mode cases; assert default `deployment_mode == "saas"` and that `secret_key` is required.
- [ ] **Step 3:** `python -m pytest tests/test_config_validation.py -v` → PASS
- [ ] **Step 4: Commit** — `git commit -am "refactor(config): drop dev mode + auth_mode, default saas"`

---

## Phase 3 — SaaS IdP (Authlib: password + GitHub/Google + invites)

### Task 3.1: Social OAuth login (GitHub + Google)

**Files:**
- Create: `server/api/src/ai_portal/auth/saas_idp/social.py`
- Modify: `server/api/src/ai_portal/core/config.py` (`oauth_github_id/secret`, `oauth_google_id/secret`)
- Test: `server/api/tests/test_saas_social.py`

**Interfaces:**
- Produces: `oauth = OAuth()` registered with `github`/`google`; `async def social_callback(provider, token_resp) -> UserClaims` (normalizes provider profile → UserClaims). Login route exchanges code, calls `jit_provision`, then `create_access_token`.

- [ ] **Step 1:** TDD `social_callback` mapping GitHub/Google userinfo → `UserClaims` (mock userinfo with respx). Step 2 verify fail. Step 3 implement with Authlib `OAuth().register(...)`. Step 4 verify pass. Step 5 commit `feat(auth): SaaS social login (github, google)`.

### Task 3.2: Password login issuing SaaS JWT

**Files:**
- Modify: `server/api/src/ai_portal/auth/router.py` (or `routes_*`), reuse existing `auth/password.py` + `create_access_token`
- Test: `server/api/tests/test_saas_password_login.py`

- [ ] TDD: register → login with password → returns access+refresh JWT (`type=access`, `sub=uuid`). Verify against `decode_token`. Commit `feat(auth): SaaS password login`.

### Task 3.3: Invite-accept flow

**Files:**
- Modify: `server/api/src/ai_portal/auth/routes_members.py` (already issues invites via `OrgInvite`)
- Create: accept endpoint `POST /auth/invites/{token}/accept`
- Test: `server/api/tests/test_invite_accept.py`

- [ ] TDD: pending `OrgInvite` + signup/login → accept token → user attached to org with invite's role, `accepted_at` set, expired/revoked rejected. Commit `feat(auth): invite-accept flow`.

---

## Phase 4 — Enterprise SSO routes

### Task 4.1: Login redirect + callback

**Files:**
- Modify: `server/api/src/ai_portal/auth/routes_sso.py` (keep OIDC; drop SAML)
- Modify: `server/api/src/ai_portal/auth/idp/providers/oidc.py` — replace `_claims_from_token` unverified base64 parse with `jwks.verify_id_token` + `make_claims`.
- Test: `server/api/tests/test_sso_oidc_flow.py`

- [ ] TDD: `/auth/sso/login` → redirect URL to issuer; `/auth/sso/callback` → verified claims → `jit_provision` → app session. Use Keycloak discovery in the E2E (Phase 8), unit-test with respx. Commit `feat(auth): enterprise OIDC SSO routes with verified id_token`.

---

## Phase 5 — Backend cleanup (delete off-path code)

Delete; prove nothing live imports it (`grep -rn "<symbol>" server/api/src --include="*.py" | grep -v __pycache__`); run smoke + suite; commit. Keep only SaaS + first-enterprise (OIDC) path.

### Task 5.1: Delete Entra / MSAL backend

- [ ] Remove `auth/strategies/entra.py`, `auth/idp/providers/entra.py`, `auth/strategies/api_key.py` (keep `portal_keys`, `jwt`), and Entra helpers in `auth/service.py` (`upsert_user_from_entra_claims`, `profile_fields_from_claims`), Entra refs in `auth/__init__.py`, `routes_me.py`, `routes_rbac.py`, `idp/providers/__init__.py`.
- [ ] Delete tests `test_auth_entra.py`. Grep-verify no imports. Run `python -m pytest tests/test_smoke_control_plane.py -v`. Commit `chore(auth): remove Entra/MSAL backend`.

### Task 5.2: Delete SAML / Okta / dev / unused strategies

- [ ] Remove `auth/idp/providers/{saml.py,okta.py}`, `auth/strategies/dev.py`. Keep `oidc.py`, `google.py` (social), `jwt.py`, `portal_keys.py`. Update `idp/registry.py` registrations. Commit `chore(auth): remove SAML/Okta/dev strategies`.

### Task 5.3: Delete LDAP / Active Directory

- [ ] Remove `auth/directory/` (whole package), `auth/routes_ldap.py`, and its router include in `main.py`/`auth/__init__.py`. Remove LDAP env from `.env.example`. Delete LDAP tests. Commit `chore(auth): remove LDAP/AD directory`.

### Task 5.4: Delete SCIM

- [ ] Remove `scim/` (whole package) and its router include. Drop SCIM env. Delete SCIM tests. Commit `chore(auth): remove SCIM`.

### Task 5.5: Delete MFA + setup + social leftovers

- [ ] Remove `auth/mfa_totp.py`, `auth/routes_mfa.py`, `auth/routes_setup.py`, `auth/new_device_notify.py` if unused; `auth/social/providers/gitlab.py` (keep github/google). Delete `test_mfa_totp.py`. Remove router includes. Commit `chore(auth): remove MFA/setup/gitlab`.

### Task 5.6: Prune dead env + audit final surface

- [ ] Remove Entra/Okta/SAML/SCIM/LDAP/MFA keys from `server/api/.env.example`. List remaining `auth/` files; confirm only: `oidc/`, `idp/providers/{oidc,google}`, `strategies/{jwt,portal_keys}`, `social/providers/{github,google}`, `password.py`, `sessions.py`, `routes_{sso,members,orgs,me,social}.py`, `service.py`, `deps.py`, `model.py`, `router.py`. Run full backend suite. Commit `chore(auth): prune dead auth env + confirm surface`.

### Task 5.7: Drop orphaned DB schema (alembic migration)

After the models are gone, their tables/columns are dead weight. Add ONE migration to drop them. **Keep `idp_connections`** — the enterprise OIDC connection stores its config there; only its SAML/Okta/Entra *rows* are stale (handled as a data delete, not schema).

**Files:**
- Create: `server/api/alembic/versions/075_drop_legacy_auth_schema.py` (down-revision `074`)
- Modify: `server/api/src/ai_portal/auth/model.py` (remove `UserMfaFactor` class + `users.entra_object_id`, `users.scim_external_id`, `users.mfa_required` columns)
- Test: `server/api/tests/test_alembic_clean_upgrade.py` (already exists — must stay green base→head)

**Drop (tables):** `scim_endpoints`, `scim_groups`, `scim_group_members`, `ldap_connections`, `user_mfa_factors`.
**Drop (columns on `users`):** `entra_object_id`, `scim_external_id`, `mfa_required`.
**Data delete (keep table):** `DELETE FROM idp_connections WHERE provider IN ('saml','okta','entra')`.

- [ ] **Step 1:** Remove the model classes/columns listed above from `auth/model.py` and `scim/model.py`/`directory/model.py` (already deleted in 5.1–5.4; confirm no `Base` still maps these tables).
- [ ] **Step 2:** Write the migration:

```python
# server/api/alembic/versions/075_drop_legacy_auth_schema.py
"""drop legacy auth schema (scim, ldap, mfa, entra/scim user cols)"""
from alembic import op
import sqlalchemy as sa

revision = "075"
down_revision = "074"
branch_labels = None
depends_on = None

_TABLES = ["scim_group_members", "scim_groups", "scim_endpoints", "ldap_connections", "user_mfa_factors"]
_USER_COLS = ["entra_object_id", "scim_external_id", "mfa_required"]


def upgrade() -> None:
    op.execute("DELETE FROM idp_connections WHERE provider IN ('saml','okta','entra')")
    for t in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    for c in _USER_COLS:
        op.execute(f"ALTER TABLE users DROP COLUMN IF EXISTS {c}")


def downgrade() -> None:
    # One-way cleanup; legacy tables are not recreated. Restore from 0xx if needed.
    raise NotImplementedError("legacy auth schema removal is not reversible")
```

- [ ] **Step 3:** Verify migration chain on a scratch DB: `DATABASE_URL=$E2E_DATABASE_URL alembic upgrade head` → no error; `python -m pytest tests/test_alembic_clean_upgrade.py -v` → PASS (base→head clean).
- [ ] **Step 4:** Grep-verify no model/code references the dropped tables/columns: `grep -rn "user_mfa_factors\|scim_\|ldap_connections\|entra_object_id\|scim_external_id\|mfa_required" src --include="*.py" | grep -v __pycache__` → empty.
- [ ] **Step 5:** Run smoke + auth suite against the migrated DB → green.
- [ ] **Step 6: Commit** — `git add -A && git commit -m "chore(db): drop legacy scim/ldap/mfa/entra schema (migration 075)"`

---

## Phase 6 — Frontend cleanup + rework

### Task 6.1: Delete MSAL / Entra frontend

**Files (delete):** `apps/frontend/src/auth/{EntraAuthGate,EntraRoot}.tsx`, `apps/frontend/src/auth/{msalConfig,msalInstance}.ts`

- [ ] Remove the files + their imports (search `EntraAuthGate`, `msalInstance`, `@azure/msal`). Remove `@azure/msal-*` from `apps/frontend/package.json`. Build: `pnpm --filter frontend build`. Commit `chore(web): remove MSAL/Entra`.

### Task 6.2: Collapse `VITE_AUTH_MODE` to single OIDC-consumer flow

**Files:** `apps/frontend/src/auth/tokenStore.ts`, `src/hooks/useAuthRedirect.ts`, `src/lib/auth-strategies.ts` (+`.test.ts`), `src/routes/__root.tsx`, any `VITE_AUTH_MODE` reader (grep), `apps/frontend/render` env.

- [ ] Remove `entra` branch; keep one token-bearer flow. Update `auth-strategies.test.ts`. Build + `pnpm --filter frontend test`. Commit `refactor(web): single OIDC-consumer auth flow`.

### Task 6.3: Login + social buttons + callback route

**Files:** `apps/frontend/src/routes/login.tsx` (read first), Create `src/routes/auth.callback.tsx`, reuse `src/components/auth/AuthShell.tsx`.

- [ ] Login: email/password form + "Continue with GitHub" / "Continue with Google" buttons (links to backend `/auth/social/{github,google}/login`). Callback route: read token from query/hash → `tokenStore.set` → redirect to `?redirect` or `/`. Keep `register.tsx` for SaaS signup; delete `setup.tsx` if dev-only. E2E selectors preserved (see Phase 8). Commit `feat(web): login with social + OAuth callback`.

### Task 6.4: Invite-accept route

**Files:** Create `apps/frontend/src/routes/invite.$token.tsx`

- [ ] Invitee lands from email link → if unauthenticated, signup/login → POST accept → land in org. Commit `feat(web): invite-accept route`.

---

## Phase 7 — Landing → app login

**Files:** `apps/landing/src/lib/app-url.ts` (exists, returns app URL), landing CTA components (grep `getAppUrl`).

- [ ] **Step 1:** Point "Sign in" / "Get started" CTAs at `getAppUrl() + "/login"` (and `/register`). Verify `VITE_APP_URL` documented for each env.
- [ ] **Step 2:** Confirm app `/login` post-login honors `?redirect=`; logout clears token → returns to landing or `/login`.
- [ ] **Step 3:** Build landing (`pnpm --filter landing build`). Commit `feat(landing): CTAs route to app login/register`.

---

## Phase 8 — Local testing (Keycloak + E2E, both modes)

### Task 8.1: Keycloak compose + seeded realms

**Files:** Create `tests/keycloak/docker-compose.yml`, `tests/keycloak/realms/vortex-saas-realm.json`, `tests/keycloak/realms/acme-corp-realm.json`, `tests/keycloak/README.md`.

- [ ] Keycloak 26 `start-dev --import-realm`, two realms (SaaS-as-our-IdP optional; `acme-corp` = customer IdP with groups `IT-Admins`/`Engineering` + `vortex-app` client + groups protocol mapper). Verify: `curl .../realms/acme-corp/.well-known/openid-configuration` and a Direct-Access-Grant token shows the `groups` claim. Commit `test(auth): keycloak compose + seeded realms`.

### Task 8.2: Enterprise SSO E2E

**Files:** Create `apps/frontend/e2e/auth/enterprise-sso.spec.ts`

- [ ] Through the UI: `/login` → redirect to Keycloak (`acme-corp`) → authenticate `alice@acme.test` → callback → JIT-provisioned → `IT-Admins`→`admin` → admin-only action allowed, member-only denial verified. Run against E2E DB (8001). Commit `test(auth): enterprise SSO E2E`.

### Task 8.3: SaaS signup + invite E2E

**Files:** Create `apps/frontend/e2e/auth/saas-signup-invite.spec.ts`

- [ ] Through the UI: register → create org → invite `bob@…` → second context accepts invite → joins org → RBAC enforced. Commit `test(auth): saas signup + invite E2E`.

### Task 8.4: Full suite green

- [ ] `pnpm test:e2e` all green; backend `DATABASE_URL=$E2E_DATABASE_URL python -m pytest tests -ra` (no unexpected skips). Fix until green. Commit `test(auth): suites green for both modes`.

---

## Phase 9 — Render deploy (SaaS correctness)

**Files:** `render.yaml`, `server/api/.env.example`, app cookie/session config.

- [ ] **Step 1:** `render.yaml` `ai-portal-api` env: `DEPLOYMENT_MODE=saas` (set), add `SECRET_KEY` (generateValue — exists), `OAUTH_GITHUB_ID/SECRET`, `OAUTH_GOOGLE_ID/SECRET` (sync:false). Remove dead `VITE_AUTH_MODE=local` from `ai-portal-app` (replace with single-flow var if any).
- [ ] **Step 2:** Set OAuth callback URLs in GitHub/Google apps → `https://<api>.onrender.com/auth/social/{github,google}/callback`. `CORS_ORIGINS` = app URL; `VITE_API_URL` = api URL; `VITE_APP_URL` = app URL on landing.
- [ ] **Step 3:** Secure session cookies (`Secure`, `SameSite=Lax`), trust Render proxy (`X-Forwarded-Proto`). Run alembic on deploy; `/health` green.
- [ ] **Step 4:** Post-deploy smoke: register → login → social login → invite → (enterprise OIDC config validated separately). Commit `chore(deploy): render env for saas auth`.

---

## Self-Review

- **Spec coverage (auth-plan §A–§H):** §A→Phase 1; dev-removal→Phase 2; §B→Phase 3; §C→Phase 4; §D code-deletes→Phase 5.1–5.6, **DB-deletes→Phase 5.7**; §E→Phase 6; §F(landing)→Phase 7; §G(testing)→Phase 8; §H(render)→Phase 9. ✓
- **DB cleanup:** drops `scim_*`, `ldap_connections`, `user_mfa_factors` tables + `users.{entra_object_id,scim_external_id,mfa_required}` cols; keeps `idp_connections` (OIDC uses it), deletes only its stale SAML/Okta/Entra rows. ✓
- **Type consistency:** `UserClaims`, `map_groups_to_role`, `jit_provision`, `verify_id_token`, `authenticate_oidc_bearer` signatures stable across phases. ✓
- **Deletion safety:** every Phase-5/6 task pairs removal with a grep-for-imports + suite run before commit. ✓
- **Known read-first steps:** frontend Tasks 6.2/6.3 and Phase 7 require reading the current component before editing (noted inline) — not placeholders, but the implementer must inspect existing JSX.
