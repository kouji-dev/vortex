# Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared substrate (tenancy, identity, RBAC, API keys, audit, usage, billing, webhooks, settings) that every other module of the suite consumes.

**Architecture:** Each capability is a self-contained domain under `server/api/src/ai_portal/<domain>/` with `model.py` (SQLAlchemy), `repository.py`, `service.py`, `router.py`, `schemas.py`. Cross-domain contracts exposed through a thin `control_plane/` facade so other modules import one shape, not many. SQLAlchemy + Alembic for migrations. FastAPI dependency-injection for `require_actor` / `require_permission` / `emit_audit` / `emit_usage` / `emit_webhook`. Identity, SCIM, billing, notification channels, blob storage and audit sinks are pluggable via `<area>/protocol.py` + `<area>/providers/<name>.py` registries.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x async, Alembic, Pydantic v2, pgvector unused here, asyncpg, pytest + pytest-asyncio, respx for HTTP mocks, python-saml + authlib for SSO, scim2-models for SCIM, stripe-python.

**Spec:** `docs/superpowers/specs/2026-05-28-control-plane-design.md`

---

## Pre-flight

- [ ] **Step P1: Confirm worktree + branch**

You are operating in a worktree off the `pivot` branch (created by orchestrator). Verify:
```bash
git status --short
git rev-parse --abbrev-ref HEAD     # expect: pivot-control-plane (or assigned)
```

- [ ] **Step P2: Install / sync dependencies**

```bash
cd server/api
uv sync                              # or `pip install -e .` if not using uv
```

Add new dependencies to `pyproject.toml`:
```toml
[project.dependencies]
# existing deps...
python3-saml = "^1.16"               # SAML 2.0
authlib = "^1.3"                     # OIDC
scim2-models = "^0.3"                # SCIM 2.0
stripe = "^10.0"                     # billing
boto3 = "^1.34"                      # S3 BlobStore
azure-storage-blob = "^12.20"        # Azure Blob BlobStore
google-cloud-storage = "^2.16"       # GCS BlobStore
cryptography = "^42.0"               # secret encryption
itsdangerous = "^2.2"                # webhook signing
```

```bash
uv lock && uv sync
```

- [ ] **Step P3: Confirm dev DB up**

```bash
curl -s http://localhost:8000/health  # dev backend; if down: pnpm dev:server
```

- [ ] **Step P4: Create empty Alembic revision for module**

```bash
cd server/api
alembic revision -m "control_plane: scaffolding" --autogenerate=false
# Note the revision ID. We will fill it across tasks.
```

---

## Phase A — Tenancy & Users (foundations)

### Task A1: Orgs domain — model + migration

**Files:**
- Create: `server/api/src/ai_portal/orgs/__init__.py`
- Create: `server/api/src/ai_portal/orgs/model.py`
- Create: `server/api/alembic/versions/<rev>_orgs.py`
- Test: `server/api/tests/orgs/test_org_model.py`

- [ ] **Step 1: Write failing test for org slug uniqueness**

```python
# server/api/tests/orgs/test_org_model.py
import pytest
from sqlalchemy.exc import IntegrityError
from ai_portal.orgs.model import Org

@pytest.mark.asyncio
async def test_org_slug_unique(db_session):
    db_session.add(Org(slug="acme", name="Acme Co"))
    await db_session.commit()
    db_session.add(Org(slug="acme", name="Other"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
```

- [ ] **Step 2: Run test (expect failure)**

```bash
pytest server/api/tests/orgs/test_org_model.py::test_org_slug_unique -xvs
# Expect: ImportError or no module 'orgs'
```

- [ ] **Step 3: Implement Org model**

```python
# server/api/src/ai_portal/orgs/model.py
from datetime import datetime
from sqlalchemy import String, DateTime, Enum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
import enum
from ai_portal.db.base import Base, uuid_pk

class OrgStatus(enum.Enum):
    active = "active"
    suspended = "suspended"
    deleted = "deleted"

class Org(Base):
    __tablename__ = "orgs"
    __table_args__ = (UniqueConstraint("slug", name="uq_orgs_slug"),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uuid_pk)
    slug: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    region: Mapped[str] = mapped_column(String(32), default="eu-west-1")
    status: Mapped[OrgStatus] = mapped_column(Enum(OrgStatus), default=OrgStatus.active)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Add alembic migration for orgs**

In the revision created in P4, add:
```python
def upgrade():
    op.create_table(
        "orgs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("region", sa.String(32), nullable=False, server_default="eu-west-1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_orgs_slug", "orgs", ["slug"])
    op.create_index("ix_orgs_slug", "orgs", ["slug"])
```

- [ ] **Step 5: Apply migration**

```bash
cd server/api && alembic upgrade head
```

- [ ] **Step 6: Run test (expect pass)**

```bash
pytest server/api/tests/orgs/test_org_model.py -xvs
```

- [ ] **Step 7: Commit**

```bash
git add server/api/src/ai_portal/orgs/ server/api/alembic/versions/ server/api/tests/orgs/
git commit -m "feat(control-plane): orgs model + migration"
```

### Task A2: Orgs repository + service

**Files:**
- Create: `server/api/src/ai_portal/orgs/repository.py`
- Create: `server/api/src/ai_portal/orgs/service.py`
- Create: `server/api/src/ai_portal/orgs/schemas.py`
- Test: `server/api/tests/orgs/test_org_service.py`

- [ ] **Step 1: Write failing test (create_org happy path + slug taken)**

```python
# server/api/tests/orgs/test_org_service.py
import pytest
from ai_portal.orgs.service import OrgService, OrgSlugTaken
from ai_portal.orgs.schemas import OrgCreate

@pytest.mark.asyncio
async def test_create_org_returns_org(db_session):
    svc = OrgService(db_session)
    org = await svc.create(OrgCreate(slug="acme", name="Acme"))
    assert org.slug == "acme"

@pytest.mark.asyncio
async def test_create_org_duplicate_slug_raises(db_session):
    svc = OrgService(db_session)
    await svc.create(OrgCreate(slug="acme", name="Acme"))
    with pytest.raises(OrgSlugTaken):
        await svc.create(OrgCreate(slug="acme", name="Other"))
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement schemas + repository + service**

```python
# schemas.py
from pydantic import BaseModel, Field
class OrgCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=255)
class OrgOut(BaseModel):
    id: str; slug: str; name: str; region: str; status: str
    class Config: from_attributes = True
```

```python
# repository.py
from sqlalchemy import select
from ai_portal.orgs.model import Org

class OrgRepo:
    def __init__(self, session): self.s = session
    async def by_slug(self, slug): return (await self.s.execute(select(Org).where(Org.slug==slug))).scalar_one_or_none()
    async def add(self, org): self.s.add(org); await self.s.flush(); return org
```

```python
# service.py
class OrgSlugTaken(Exception): pass
class OrgService:
    def __init__(self, session): self.repo = OrgRepo(session); self.s = session
    async def create(self, dto: OrgCreate) -> Org:
        if await self.repo.by_slug(dto.slug): raise OrgSlugTaken(dto.slug)
        org = Org(slug=dto.slug, name=dto.name)
        await self.repo.add(org); await self.s.commit(); return org
```

- [ ] **Step 4: Run (expect pass)**, **Step 5: Commit**

```bash
git commit -am "feat(control-plane): orgs service + repo + schemas"
```

### Task A3: Users + sessions migration & model

**Files:**
- Create: `server/api/src/ai_portal/users/model.py` (Users, UserSession, UserMfaFactor)
- Create: `server/api/src/ai_portal/users/repository.py`
- Create: `server/api/src/ai_portal/users/service.py` (signup, verify_email, password_reset)
- Create: `server/api/src/ai_portal/users/schemas.py`
- Migration: extend the control-plane revision with `users`, `user_sessions`, `user_mfa_factors`
- Test: `server/api/tests/users/test_user_signup.py`, `test_password_reset.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/users/test_user_signup.py
import pytest
from ai_portal.users.service import UserService, EmailNotVerified
from ai_portal.users.schemas import SignupRequest

@pytest.mark.asyncio
async def test_signup_creates_user_and_sends_verify(db_session, notify_capture):
    svc = UserService(db_session)
    user = await svc.signup(SignupRequest(email="a@b.com", password="Strong-pass-123"))
    assert user.email == "a@b.com"
    assert notify_capture.has(template="verify_email", to="a@b.com")
    with pytest.raises(EmailNotVerified):
        await svc.assert_can_login("a@b.com")
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement model + service** (Users: id, email-unique, password_hash, name, locale, mfa_required, email_verified_at, created_at; sessions: id, user_id, token_hash, ip, ua, created_at, expires_at, revoked_at). Hash passwords with `argon2`.

- [ ] **Step 4: Add migration tables**, **Step 5: Apply + test + commit**

```bash
git commit -am "feat(control-plane): users + signup with verify-email"
```

### Task A4: Org membership + invitations

**Files:**
- Create: `server/api/src/ai_portal/orgs/membership_model.py` (OrgMember, OrgInvitation)
- Modify: `server/api/src/ai_portal/orgs/service.py` (add invite, accept_invitation, remove_member)
- Test: `server/api/tests/orgs/test_invitations.py`

- [ ] **Step 1–6: TDD-cycle**

Test scenarios: invite emits notification, invite token verifies, accept assigns role, expired token rejected, remove member revokes sessions + scopes keys (mocked).

```python
@pytest.mark.asyncio
async def test_invite_then_accept(db_session, notify_capture):
    org = await OrgService(db_session).create(OrgCreate(slug="acme", name="Acme"))
    inv = await OrgService(db_session).invite(org.id, email="x@acme.com", role="member", by="founder-user-id")
    assert notify_capture.has(template="org_invitation", to="x@acme.com")
    user = await UserService(db_session).signup_via_invite(inv.token, password="Strong-pass-123")
    assert await OrgService(db_session).is_member(org.id, user.id)
```

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(control-plane): org invitations + membership"
```

---

## Phase B — Permissions catalog + RBAC

### Task B1: Permission catalog seed

**Files:**
- Create: `server/api/src/ai_portal/rbac/catalog.py` (single source of truth for permission keys across all modules)
- Migration: `permissions` table seed
- Test: `server/api/tests/rbac/test_catalog.py`

```python
# catalog.py
PERMISSIONS = [
    # control plane
    ("org:read", "Read org metadata"),
    ("org:update", "Update org metadata"),
    ("members:read", ...),
    ("members:invite", ...),
    ("api-keys:create", ...),
    ("audit:read", ...),
    ("usage:read", ...),
    ("budgets:write", ...),
    ("webhooks:write", ...),
    ("settings:write", ...),
    # gateway
    ("gateway:complete", "Call LLMs through gateway"),
    ("gateway:embed", "Call embedder"),
    ("gateway:admin", "Manage routing/rate-limits/policies"),
    ("gateway:traces:read", "View traces"),
    ("gateway:replay", "Replay historic requests"),
    # rag
    ("kb:create", ...), ("kb:read", ...), ("kb:write", ...), ("kb:delete", ...),
    ("kb:answer", ...), ("kb:eval", ...),
    # memories
    ("memory:read", ...), ("memory:write", ...), ("memory:admin", ...),
    # workers
    ("workers:submit", ...), ("workers:approve", ...), ("workers:admin", ...),
]
```

- [ ] **Step 1: Write test** asserting catalog imports + ≥30 permissions defined and unique keys.
- [ ] **Step 2–6**: Implement, write seed migration, run, commit.

```bash
git commit -m "feat(control-plane): permission catalog (all modules)"
```

### Task B2: Roles + assignments

**Files:**
- Create: `server/api/src/ai_portal/rbac/model.py` (Role, RolePermission, ActorRoleAssignment)
- Modify: `server/api/src/ai_portal/rbac/service.py`
- Migration extension
- Test: `server/api/tests/rbac/test_role_assignment.py`

- [ ] **Step 1: Failing test — actor with `owner` role passes any permission check; with `viewer` fails write checks**
- [ ] **Step 2–6**: Implement built-in roles seed (`owner`, `admin`, `member`, `viewer`, `service`), `has_permission(actor, perm, resource=None)`, commit.

```bash
git commit -m "feat(control-plane): RBAC roles + assignments"
```

### Task B3: FastAPI dependencies — require_actor / require_permission

**Files:**
- Create: `server/api/src/ai_portal/control_plane/deps.py`
- Test: `server/api/tests/control_plane/test_deps.py`

```python
# deps.py
from fastapi import Depends, HTTPException
from ai_portal.auth.deps import current_actor

def require_permission(perm: str):
    async def _dep(actor = Depends(current_actor), rbac = Depends(get_rbac_service)):
        if not await rbac.has_permission(actor, perm):
            raise HTTPException(403, detail=f"missing permission: {perm}")
        return actor
    return _dep
```

- [ ] **Step 1: Test** that a route guarded by `require_permission("kb:create")` returns 403 for viewer and 200 for admin.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): require_permission dep"
```

---

## Phase C — API Keys

### Task C1: API key model + hashing

**Files:**
- Create: `server/api/src/ai_portal/api_keys/model.py`, `repository.py`, `service.py`, `schemas.py`
- Migration extension
- Test: `server/api/tests/api_keys/test_create_key.py`, `test_verify_key.py`

Storage: random 32-byte secret → prefix `ap_` + base62; persist `hash = sha256(secret)`; show secret once.

- [ ] **Step 1: Failing test**

```python
async def test_create_key_returns_plaintext_once(db_session):
    svc = ApiKeyService(db_session)
    created = await svc.create(org_id=ORG, actor_user_id=USR, name="dev", scopes=["gateway:complete"])
    assert created.plaintext.startswith("ap_")
    # secret accessible only on creation
    assert await svc.verify(created.plaintext) == created.key
```

- [ ] **Step 2–6**: Implement; verify never returns the plaintext from DB; rotation = create new + revoke old.

```bash
git commit -m "feat(control-plane): api keys (mint/verify/revoke)"
```

### Task C2: Bearer auth strategy (api-key)

**Files:**
- Modify: `server/api/src/ai_portal/auth/strategies/` → add `api_key.py`
- Test: `server/api/tests/auth/test_api_key_strategy.py`

- [ ] **Step 1: Failing test** — request with `Authorization: Bearer ap_xxx` resolves an Actor whose `kind="api_key"` and `scopes` populated.
- [ ] **Step 2–6**: Implement strategy, integrate into `current_actor` resolver chain, commit.

```bash
git commit -m "feat(control-plane): api-key bearer strategy"
```

---

## Phase D — Audit log (chained, immutable)

### Task D1: Audit model + Merkle hash

**Files:**
- Create: `server/api/src/ai_portal/audit/model.py` (already exists — refactor), `repository.py`, `service.py`
- Migration: `audit_events(id, org_id, actor_json, action, resource_type, resource_id, payload_json, prev_hash, hash, ts)` partitioned by month
- Test: `server/api/tests/audit/test_chain_integrity.py`

```python
def compute_hash(event_id, org_id, action, resource_type, resource_id, payload, ts, prev_hash):
    h = hashlib.sha256()
    for f in (event_id, org_id, action, resource_type, str(resource_id or ""), json.dumps(payload, sort_keys=True), ts.isoformat(), prev_hash or ""):
        h.update(f.encode()); h.update(b"\0")
    return h.hexdigest()
```

- [ ] **Step 1: Failing test** — write 3 events; recompute chain; tamper with payload of event 2; chain detects mismatch.
- [ ] **Step 2–6**: Implement append-only path; raise on UPDATE/DELETE attempts (DB trigger or service guard); commit.

```bash
git commit -m "feat(control-plane): audit log with hash chain"
```

### Task D2: emit_audit helper + AuditSink abstraction

**Files:**
- Create: `server/api/src/ai_portal/audit/protocol.py` (`AuditSink`)
- Create: `server/api/src/ai_portal/audit/sinks/postgres.py`, `s3_jsonl.py`, `splunk_hec.py`, `datadog_logs.py`, `syslog.py`
- Create: `server/api/src/ai_portal/audit/registry.py`
- Test: `server/api/tests/audit/test_sinks.py`

```python
# protocol.py
class AuditSink(Protocol):
    async def write(self, event: AuditEvent) -> None: ...
    async def query(self, f: AuditFilter) -> list[AuditEvent]: ...
```

- [ ] **Step 1: Failing tests** per sink (mock HTTP for HEC + Datadog).
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): audit sink abstraction + bundled sinks"
```

### Task D3: Audit search + export endpoints

**Files:**
- Modify: `server/api/src/ai_portal/audit/router.py`
- Test: `server/api/tests/audit/test_router_search_export.py`

- [ ] **Step 1: Failing test** — GET `/v1/audit-events?action=org:update&from=...&to=...` paginates; POST `/v1/audit-events:export` enqueues job.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): audit search + export endpoints"
```

---

## Phase E — Usage metering + budgets

### Task E1: usage_events + emit_usage

**Files:**
- Modify: `server/api/src/ai_portal/usage/model.py` (existing — extend)
- Migration: ensure monthly partitioning
- Test: `server/api/tests/usage/test_emit_usage.py`

Units: `tokens_in`, `tokens_out`, `tokens_cache_read`, `tokens_cache_write`, `embeddings`, `documents_ingested`, `queries`, `worker_minutes`, `storage_gb`.

- [ ] **Step 1: Failing test** — emit_usage writes row with cost computed from pricing snapshot.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): emit_usage + units catalog"
```

### Task E2: Rollups + dashboard endpoint

**Files:**
- Create: `server/api/src/ai_portal/usage/rollups.py` (hourly job)
- Modify: `usage/router.py` (`GET /v1/usage?dim=user|team|key|model|module&period=...`)
- Test: `tests/usage/test_rollups.py`

- [ ] **Step 1: Failing test** — emit 10 events across 2 keys, rollup, query → returns 2 rows summed correctly.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): usage rollups + dashboard endpoint"
```

### Task E3: Quotas + budgets (hard cutoff)

**Files:**
- Create: `server/api/src/ai_portal/budgets/model.py`, `service.py`, `router.py`, `schemas.py`
- Migration: `quotas`, `budgets`, `budget_alerts`
- Test: `tests/budgets/test_budget_cutoff.py`

- [ ] **Step 1: Failing test** — `check_and_charge(actor, scope, cost_cents)` returns `BudgetExceeded` when accumulated > limit. Soft warnings at 50/80/100.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): quotas + budgets with soft warns + hard cutoff"
```

---

## Phase F — Webhooks (outbound)

### Task F1: Webhook model + signing

**Files:**
- Create: `server/api/src/ai_portal/webhooks/model.py`, `signer.py`, `service.py`, `router.py`, `schemas.py`
- Migration: `webhooks`, `webhook_deliveries`, `webhook_event_types`
- Test: `tests/webhooks/test_signing.py`

```python
def sign(payload: bytes, secret: bytes) -> str:
    return "v1=" + hmac.new(secret, payload, hashlib.sha256).hexdigest()
```

- [ ] **Step 1: Failing test** — verify signature reproducibility.
- [ ] **Step 2–6**: Implement; commit.

```bash
git commit -m "feat(control-plane): webhook model + signing"
```

### Task F2: Delivery worker + retry

**Files:**
- Create: `server/api/src/ai_portal/webhooks/worker.py` (asyncio task, exponential backoff up to 24h)
- Test: `tests/webhooks/test_delivery_retry.py` (use respx; assert attempts schedule)

- [ ] **Step 1: Failing test** — first attempt 5xx → schedule retry at +30s, then +2m, then +10m … capped at 24h.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): webhook delivery worker with retry"
```

### Task F3: Event types registry + emit_webhook

**Files:**
- Create: `server/api/src/ai_portal/webhooks/event_types.py` (catalog; modules register theirs at import)
- Modify: `webhooks/service.py` add `emit_webhook(event_type, payload, org_id)`
- Test: `tests/webhooks/test_emit.py`

- [ ] **Step 1: Failing test** — calling `emit_webhook("budget.exceeded", payload, org)` enqueues delivery for every webhook subscribed to that type.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): emit_webhook + event-type registry"
```

---

## Phase G — Identity Provider (SSO) abstraction

### Task G1: IdentityProvider protocol + idp_connections model

**Files:**
- Create: `server/api/src/ai_portal/auth/idp/protocol.py`
- Create: `server/api/src/ai_portal/auth/idp/model.py` (IdpConnection)
- Migration: `idp_connections`
- Test: `tests/auth/idp/test_protocol_compliance.py`

```python
# protocol.py
class IdentityProvider(Protocol):
    name: str
    async def initiate(self, state: str, org: Org) -> str: ...        # returns redirect URL
    async def complete(self, request) -> UserClaims: ...
```

- [ ] **Step 1: Failing test** — fake provider implements protocol; registry resolves by name.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): IdP protocol + connections model"
```

### Task G2: OIDC provider (authlib)

**Files:**
- Create: `server/api/src/ai_portal/auth/idp/providers/oidc.py`
- Test: `tests/auth/idp/test_oidc.py` (respx stubs discovery + token endpoints)

- [ ] **Step 1: Failing test** — `initiate` returns URL containing `redirect_uri`, `state`, `code_challenge` (PKCE). `complete` exchanges code → claims with email + sub.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): OIDC IdP (authlib)"
```

### Task G3: SAML provider (python3-saml)

**Files:**
- Create: `server/api/src/ai_portal/auth/idp/providers/saml.py`
- Test: `tests/auth/idp/test_saml.py` (signed assertion fixture)

- [ ] **Step 1: Failing test** — `complete` verifies SAML response signature + extracts claims.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): SAML IdP (python3-saml)"
```

### Task G4: Entra / Okta / Google presets

**Files:**
- Create: `server/api/src/ai_portal/auth/idp/providers/entra.py`, `okta.py`, `google.py` (each is a thin wrapper that fills OIDC discovery URL + scopes)
- Test: one test per preset asserting redirect URL contains the expected authorize host.

- [ ] **Step 1–6**: Implement each, commit individually.

```bash
git commit -m "feat(control-plane): IdP presets (Entra, Okta, Google)"
```

### Task G5: SSO routes + domain auto-route

**Files:**
- Modify: `server/api/src/ai_portal/auth/router.py` (add `/v1/auth/sso/start`, `/v1/auth/sso/callback`)
- Modify: service to JIT-provision user on first login
- Test: `tests/auth/test_sso_flow.py`

- [ ] **Step 1: Failing test** — `/v1/auth/sso/start?email=alice@acme.com` resolves Acme's IdP by domain → 302 to provider URL. Callback creates user + session.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): SSO start/callback + JIT user provisioning"
```

### Task G6: SSO-required enforcement

**Files:**
- Modify: `auth/service.py` (reject password login when org policy = sso_required and user belongs to that org)
- Test: `tests/auth/test_sso_required.py`

- [ ] **Step 1: Failing test** — password login → 403 with `sso_required` error.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): enforce sso-required org policy"
```

---

## Phase H — SCIM provisioning

### Task H1: SCIM router + tokens

**Files:**
- Create: `server/api/src/ai_portal/scim/router.py`, `service.py`, `schemas.py`, `model.py` (ScimEndpoint, ScimToken)
- Migration: `scim_endpoints`, `scim_tokens`
- Test: `tests/scim/test_scim_users.py`

- [ ] **Step 1: Failing tests** — `POST /scim/v2/Users` with valid Bearer token creates user; deactivate (`active=false`) revokes sessions; group → role mapping applies.
- [ ] **Step 2–6**: Implement using `scim2-models`; commit.

```bash
git commit -m "feat(control-plane): SCIM 2.0 users + groups"
```

### Task H2: SCIM presets (Okta, Entra)

**Files:**
- Create: `server/api/src/ai_portal/scim/presets/okta.py`, `entra.py` (attribute mappers)
- Test: `tests/scim/test_presets.py`

- [ ] **Step 1–6**: Implement attribute mappers (e.g., Entra `objectId` → external_id); test with sample SCIM payloads; commit.

```bash
git commit -m "feat(control-plane): SCIM Okta + Entra presets"
```

---

## Phase I — Notification channels

### Task I1: Channel protocol + in_app + smtp

**Files:**
- Create: `server/api/src/ai_portal/notify/protocol.py` (`Channel`), `notify/channels/in_app.py`, `smtp.py`, `service.py`, `model.py` (Notification, UserNotificationPref)
- Test: `tests/notify/test_smtp.py` (mock SMTP), `test_in_app.py`

```python
class Channel(Protocol):
    async def send(self, recipient: str, template_id: str, payload: dict) -> None: ...
```

- [ ] **Step 1: Failing tests**, **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): notification channels (smtp, in_app)"
```

### Task I2: SES, SendGrid, Slack webhook

**Files:**
- Create: `notify/channels/ses.py`, `sendgrid.py`, `slack_webhook.py`
- Test: one per channel with respx

- [ ] **Step 1–6**: Implement each, commit (3 commits or one batched).

```bash
git commit -m "feat(control-plane): notification channels (ses, sendgrid, slack)"
```

### Task I3: User preference matrix

**Files:**
- Modify: `notify/service.py` add `send_event(user_id, event_type, payload)` that resolves user's per-event channel prefs and fans out.
- Test: `tests/notify/test_pref_matrix.py`

- [ ] **Step 1–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): notification user preferences"
```

---

## Phase J — Object storage (BlobStore)

### Task J1: BlobStore protocol + s3 + local

**Files:**
- Create: `server/api/src/ai_portal/storage/protocol.py`
- Create: `storage/providers/s3.py`, `local_fs.py`, `minio.py`, `azure_blob.py`, `gcs.py`
- Test: `tests/storage/test_blobstore.py`

```python
class BlobStore(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> str: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    async def presign_get(self, key: str, expires_in: int) -> str: ...
    async def presign_put(self, key: str, content_type: str, expires_in: int) -> str: ...
```

- [ ] **Step 1: Failing test** per provider with moto / fake server.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): BlobStore abstraction + 5 providers"
```

---

## Phase K — Billing

### Task K1: BillingProvider protocol + manual

**Files:**
- Create: `server/api/src/ai_portal/billing/protocol.py`
- Create: `billing/providers/manual.py` (no-op, prints invoice)
- Migration: `subscriptions`, `invoices`
- Test: `tests/billing/test_manual.py`

```python
class BillingProvider(Protocol):
    async def create_customer(self, org: Org) -> str: ...
    async def update_subscription(self, customer_id: str, plan: Plan) -> Subscription: ...
    async def report_usage(self, customer_id: str, unit: str, qty: int, ts: datetime) -> None: ...
    async def void(self, subscription_id: str) -> None: ...
```

- [ ] **Step 1–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): billing protocol + manual provider"
```

### Task K2: Stripe provider

**Files:**
- Create: `billing/providers/stripe.py`
- Test: `tests/billing/test_stripe.py` (mock with `stripe.api_base = local`)

- [ ] **Step 1: Failing test** — `create_customer` calls Stripe API and stores returned id; `report_usage` calls `SubscriptionItem.create_usage_record`.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): Stripe billing provider"
```

### Task K3: Billing router + Stripe webhook receiver

**Files:**
- Modify: `billing/router.py` add `/v1/billing/subscription`, `/v1/billing/invoices`, `/v1/billing/webhook`
- Test: `tests/billing/test_webhook.py` (signed Stripe event)

- [ ] **Step 1–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): billing routes + Stripe webhook"
```

---

## Phase L — Settings + module flags

### Task L1: Settings KV + module flags

**Files:**
- Create: `server/api/src/ai_portal/settings/model.py` (`OrgSetting`, `ModuleFlag`), `service.py`, `router.py`
- Migration: `org_settings`, `module_flags`
- Test: `tests/settings/test_module_flag.py`

- [ ] **Step 1: Failing test** — `is_module_enabled(org, "gateway")` defaults true; admin disables → returns false; gateway route guarded by `assert_module_enabled` returns 503.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): org settings + module flags"
```

---

## Phase M — Security (MFA, sessions, brute-force)

### Task M1: TOTP MFA

**Files:**
- Create: `server/api/src/ai_portal/auth/mfa_totp.py`
- Modify: login flow to require TOTP step when factor exists
- Test: `tests/auth/test_mfa_totp.py`

- [ ] **Step 1: Failing test** — enroll → return secret + QR-code data URI; verify code; login forces TOTP.
- [ ] **Step 2–6**: Implement (use `pyotp`); commit.

```bash
git commit -m "feat(control-plane): MFA (TOTP)"
```

### Task M2: Session listing + revoke

**Files:**
- Modify: `auth/router.py` add `/v1/auth/sessions`, `DELETE /v1/auth/sessions/{id}`
- Test: `tests/auth/test_session_revoke.py`

- [ ] **Step 1–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): session listing + revoke"
```

### Task M3: Brute-force limiter on /auth/login

**Files:**
- Create: `auth/limiter.py` (sliding window, per ip + email)
- Test: `tests/auth/test_bruteforce.py`

- [ ] **Step 1: Failing test** — 10 failed attempts in 60s → 429.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): brute-force protection on login"
```

---

## Phase N — GDPR data lifecycle

### Task N1: data_export_jobs + worker

**Files:**
- Create: `server/api/src/ai_portal/gdpr/export_service.py`, `export_worker.py`
- Migration: `data_export_jobs`
- Test: `tests/gdpr/test_export.py`

- [ ] **Step 1: Failing test** — request export → worker iterates registered "exporters" (one per module declares its tables) → writes zip to BlobStore → presigned URL emailed.
- [ ] **Step 2–6**: Implement; expose `register_exporter(module_name, async fn(org_id) -> dict)` registry; commit.

```bash
git commit -m "feat(control-plane): GDPR data export (Article 15)"
```

### Task N2: data_delete_jobs + cascade hook

**Files:**
- Create: `gdpr/delete_service.py`, `delete_worker.py`
- Test: `tests/gdpr/test_delete.py`

- [ ] **Step 1: Failing test** — request delete → worker invokes registered deleters (each module registers cascade) → all rows for that subject removed within job SLA → audit event written.
- [ ] **Step 2–6**: Implement; expose `register_deleter(...)`; commit.

```bash
git commit -m "feat(control-plane): GDPR data delete (Article 17) + cascade registry"
```

---

## Phase O — Admin UI

### Task O1: Frontend scaffolding

**Files:**
- Modify: `apps/frontend/src/routes/admin/index.tsx` (new), and child routes for each admin page
- Create: `apps/frontend/src/lib/admin-types.ts`

- [ ] **Step 1: Failing UI test** — `e2e/admin-shell.spec.ts` checks Admin nav lists: Members, SSO, SCIM, API Keys, Audit, Usage, Budgets, Webhooks, Billing, Settings, Data. (Defer — admin shell only.)
- [ ] **Step 2–6**: Implement shell + Members page (read-only first); commit.

```bash
git commit -m "feat(control-plane): admin shell + Members page"
```

### Task O2..On: per-page admin features

Repeat the page pattern for each admin section: SSO, SCIM, API Keys, Audit log viewer, Usage charts (use Recharts), Budgets editor, Webhooks list, Billing summary, Settings tabs (incl. module toggles), Data Export/Delete.

For each page:
- [ ] Wire React Query hook to existing API
- [ ] Render table + filters
- [ ] Add create/edit dialog if applicable
- [ ] Commit `feat(control-plane): admin <page>`

Estimate: 10 sub-tasks, one commit each.

---

## Phase P — Cross-module facade

### Task P1: Public internal API

**Files:**
- Create: `server/api/src/ai_portal/control_plane/__init__.py` re-exporting:
  - `require_actor`, `require_permission`, `emit_audit`, `emit_usage`, `emit_webhook`, `get_org_setting`, `is_module_enabled`, `BlobStore` factory, `notify_send`, `register_exporter`, `register_deleter`
- Test: `tests/control_plane/test_facade.py` (imports work; types stable)

- [ ] **Step 1–6**: Implement, commit.

```bash
git commit -m "feat(control-plane): public facade for cross-module imports"
```

---

## Final checks

- [ ] **Step F1: Run only touched-file unit tests**

For every file you modified, run `pytest <its test path> -x`. Do NOT run the full suite. Do NOT run E2E.

- [ ] **Step F2: Lint**

```bash
cd server/api && ruff check src/ai_portal --fix
ruff format src/ai_portal
```

- [ ] **Step F3: Type check**

```bash
mypy src/ai_portal
```

- [ ] **Step F4: Migration round-trip**

```bash
alembic downgrade -1 && alembic upgrade head
```

- [ ] **Step F5: Hand off to orchestrator**

Report:
- All Phase A–P tasks completed: yes/no
- Number of commits made on this worktree
- Any deferred items (with reason)
- DO NOT write E2E tests. DO NOT run E2E. The orchestrator runs E2E once at the end across all modules.

---

## Out of scope (deferred per spec)

- Multi-region / BYOK / white-label / WebAuthn / SCIM v1.1 / on-prem deploy guide / inbound audit ingestion
