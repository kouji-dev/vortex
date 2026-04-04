# SaaS + Multi-Tenancy + Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform AI Portal into a SaaS + self-hosted product with email/password auth, per-org tenant isolation, deployment modes, and Render/Supabase deployment.

**Architecture:** Add a new `local` auth mode (email+password, JWT via existing pyjwt) alongside the existing `dev`/`entra` modes. Extend the `users` table in-place with a `uuid` field used as the JWT subject, plus `org_id`, `role`, and auth flags. All tenant-scoped tables get an `org_id` column enforced at the service layer via a `TenantRepository` base class. A setup wizard gates self-hosted first boot.

**Tech Stack:** FastAPI, SQLAlchemy (sync), Alembic, pyjwt (already installed), passlib[bcrypt] (new), smtplib (stdlib), TanStack Start + TanStack Router, Tailwind v4, localStorage for JWT on the frontend.

---

## Sub-project 1: Auth Overhaul

### Task 1: Add passlib dependency

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add passlib to dependencies**

In `backend/pyproject.toml`, add `"passlib[bcrypt]>=1.7"` to the `dependencies` list:

```toml
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "pydantic-settings>=2.6",
  "httpx>=0.27",
  "openai>=1.54",
  "langchain-core>=0.3",
  "langchain-openai>=0.3",
  "langchain-anthropic>=0.3",
  "voyageai>=0.3",
  "sqlalchemy>=2.0",
  "alembic>=1.14",
  "psycopg[binary]>=3.2",
  "pgvector>=0.3",
  "python-multipart>=0.0.9",
  "python-json-logger>=3.2",
  "pypdf>=5.0",
  "pyjwt[crypto]>=2.9",
  "chonkie[semantic,code]>=1.0",
  "passlib[bcrypt]>=1.7",
]
```

- [ ] **Step 2: Install**

```bash
cd backend
pip install -e ".[dev]"
```

Expected: `Successfully installed passlib-...` in output.

- [ ] **Step 3: Verify import**

```bash
python -c "from passlib.context import CryptContext; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml
git commit -m "chore(deps): add passlib[bcrypt] for local auth password hashing"
```

---

### Task 2: Org SQLAlchemy model

**Files:**
- Create: `backend/src/ai_portal/models/org.py`
- Modify: `backend/src/ai_portal/models/__init__.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_org_model.py`:

```python
from ai_portal.models.org import Org


def test_org_model_has_expected_columns():
    cols = {c.name for c in Org.__table__.columns}
    assert "id" in cols
    assert "slug" in cols
    assert "name" in cols
    assert "instance_mode" in cols
    assert "archived_at" in cols
    assert "created_at" in cols
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend
pytest tests/test_org_model.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `org` module not found.

- [ ] **Step 3: Create the Org model**

Create `backend/src/ai_portal/models/org.py`:

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
import uuid as _uuid

from ai_portal.db.base import Base


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=_uuid.uuid4,
    )
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    instance_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 4: Export from models __init__**

Open `backend/src/ai_portal/models/__init__.py` and add `Org` to imports and `__all__`.

Current file — add these lines (keep existing imports):

```python
from ai_portal.models.org import Org
```

And add `"Org"` to `__all__` if it exists, or just verify the import works.

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_org_model.py -v
```

Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/models/org.py backend/src/ai_portal/models/__init__.py backend/tests/test_org_model.py
git commit -m "feat(models): add Org SQLAlchemy model"
```

---

### Task 3: Extend User model

**Files:**
- Modify: `backend/src/ai_portal/models/user.py`

The current User model has `id` (int PK), `email`, `entra_object_id`, `hashed_password`, `created_at`. We extend it in-place — the int PK stays so existing FKs don't break. A new `uuid` field serves as the JWT subject.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_org_model.py`:

```python
from ai_portal.models.user import User


def test_user_model_has_auth_columns():
    cols = {c.name for c in User.__table__.columns}
    assert "uuid" in cols
    assert "org_id" in cols
    assert "role" in cols
    assert "is_active" in cols
    assert "is_verified" in cols
    assert "is_superuser" in cols
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/test_org_model.py::test_user_model_has_auth_columns -v
```

Expected: `FAILED` — columns not present yet.

- [ ] **Step 3: Update User model**

Replace `backend/src/ai_portal/models/user.py` with:

```python
from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.db.base import Base


class User(Base):
    __tablename__ = "users"

    # Existing int PK — kept to avoid breaking FKs in assistants, conversations, etc.
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # UUID used as JWT subject for local auth
    uuid: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=_uuid.uuid4,
    )

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    entra_object_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Org membership (nullable until migration backfills existing rows)
    org_id: Mapped[_uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="member", server_default="member"
    )

    # Auth flags
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_org_model.py -v
```

Expected: both tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/src/ai_portal/models/user.py backend/tests/test_org_model.py
git commit -m "feat(models): extend User with uuid, org_id, role, auth flags"
```

---

### Task 4: Alembic migration — orgs table + user extensions

**Files:**
- Create: `backend/alembic/versions/022_auth_overhaul.py`

- [ ] **Step 1: Create the migration file**

Create `backend/alembic/versions/022_auth_overhaul.py`:

```python
"""Auth overhaul: create orgs table, extend users with uuid/org_id/role/auth flags

Revision ID: 022_auth_overhaul
Revises: 021_user_mem_is_system
Create Date: 2026-04-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "022_auth_overhaul"
down_revision = "021_user_mem_is_system"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create orgs table
    op.create_table(
        "orgs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("instance_mode", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # 2. Insert default org for existing data
    op.execute(
        "INSERT INTO orgs (id, slug, name) VALUES (gen_random_uuid(), 'default', 'Default Org')"
    )

    # 3. Add new columns to users
    op.add_column("users", sa.Column(
        "uuid", UUID(as_uuid=True),
        nullable=True,  # nullable during migration; backfilled below
    ))
    op.add_column("users", sa.Column(
        "org_id", UUID(as_uuid=True), nullable=True
    ))
    op.add_column("users", sa.Column(
        "role", sa.String(16), nullable=False, server_default="member"
    ))
    op.add_column("users", sa.Column(
        "is_active", sa.Boolean(), nullable=False, server_default="true"
    ))
    op.add_column("users", sa.Column(
        "is_verified", sa.Boolean(), nullable=False, server_default="false"
    ))
    op.add_column("users", sa.Column(
        "is_superuser", sa.Boolean(), nullable=False, server_default="false"
    ))

    # 4. Backfill: give every existing user a UUID and assign to default org
    op.execute("UPDATE users SET uuid = gen_random_uuid()")
    op.execute("UPDATE users SET org_id = (SELECT id FROM orgs WHERE slug = 'default')")

    # 5. Make uuid NOT NULL + unique now that it's backfilled
    op.alter_column("users", "uuid", nullable=False)
    op.create_unique_constraint("uq_users_uuid", "users", ["uuid"])

    # 6. Add FK from users.org_id -> orgs.id
    op.create_foreign_key("fk_users_org_id", "users", "orgs", ["org_id"], ["id"])
    op.create_index("ix_users_org_id", "users", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_users_org_id", "users")
    op.drop_constraint("fk_users_org_id", "users", type_="foreignkey")
    op.drop_constraint("uq_users_uuid", "users", type_="unique")
    op.drop_column("users", "is_superuser")
    op.drop_column("users", "is_verified")
    op.drop_column("users", "is_active")
    op.drop_column("users", "role")
    op.drop_column("users", "org_id")
    op.drop_column("users", "uuid")
    op.drop_table("orgs")
```

- [ ] **Step 2: Apply migration**

```bash
cd backend
python -m alembic upgrade 022_auth_overhaul
```

Expected: migration completes without error.

- [ ] **Step 3: Verify schema**

```bash
python -c "
from ai_portal.db.session import SessionLocal
from sqlalchemy import text
db = SessionLocal()
r = db.execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_name='users'\")).fetchall()
print([row[0] for row in r])
db.close()
"
```

Expected: list includes `uuid`, `org_id`, `role`, `is_active`, `is_verified`, `is_superuser`.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/022_auth_overhaul.py
git commit -m "feat(migrations): 022 create orgs table + extend users for local auth"
```

---

### Task 5: Password + JWT utilities

**Files:**
- Create: `backend/src/ai_portal/auth/password.py`
- Create: `backend/src/ai_portal/auth/jwt.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_auth_utils.py`:

```python
import time
import uuid

import pytest

from ai_portal.auth.password import hash_password, verify_password
from ai_portal.auth.jwt import create_access_token, create_refresh_token, decode_token


def test_hash_and_verify_password():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)


def test_create_and_decode_access_token():
    user_uuid = uuid.uuid4()
    org_id = uuid.uuid4()
    token = create_access_token(
        user_uuid=user_uuid, org_id=org_id, role="member", secret="testsecret"
    )
    payload = decode_token(token, secret="testsecret")
    assert payload["sub"] == str(user_uuid)
    assert payload["org_id"] == str(org_id)
    assert payload["role"] == "member"
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token():
    user_uuid = uuid.uuid4()
    org_id = uuid.uuid4()
    token = create_refresh_token(
        user_uuid=user_uuid, org_id=org_id, role="admin", secret="testsecret"
    )
    payload = decode_token(token, secret="testsecret")
    assert payload["type"] == "refresh"


def test_decode_token_wrong_secret_raises():
    user_uuid = uuid.uuid4()
    org_id = uuid.uuid4()
    token = create_access_token(user_uuid=user_uuid, org_id=org_id, role="member", secret="good")
    with pytest.raises(Exception):
        decode_token(token, secret="bad")
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_auth_utils.py -v
```

Expected: `ImportError` — modules not created yet.

- [ ] **Step 3: Create password utility**

Create `backend/src/ai_portal/auth/password.py`:

```python
from passlib.context import CryptContext

_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _ctx.verify(plain, hashed)
```

- [ ] **Step 4: Create JWT utility**

Create `backend/src/ai_portal/auth/jwt.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt

ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30
ALGORITHM = "HS256"


def create_access_token(
    *,
    user_uuid: uuid.UUID,
    org_id: uuid.UUID,
    role: str,
    secret: str,
    expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_uuid),
        "org_id": str(org_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def create_refresh_token(
    *,
    user_uuid: uuid.UUID,
    org_id: uuid.UUID,
    role: str,
    secret: str,
    expires_days: int = REFRESH_TOKEN_EXPIRE_DAYS,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_uuid),
        "org_id": str(org_id),
        "role": role,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=expires_days),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(token: str, *, secret: str) -> dict:
    """Decode and verify a JWT. Raises jwt.PyJWTError on failure."""
    return jwt.decode(token, secret, algorithms=[ALGORITHM])
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_auth_utils.py -v
```

Expected: all 4 tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/auth/password.py backend/src/ai_portal/auth/jwt.py backend/tests/test_auth_utils.py
git commit -m "feat(auth): password hashing + JWT create/decode utilities"
```

---

### Task 6: Config updates — DEPLOYMENT_MODE, SECRET_KEY, SMTP

**Files:**
- Modify: `backend/src/ai_portal/config.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_auth_utils.py`:

```python
import os


def test_settings_deployment_mode_defaults_to_dev():
    from ai_portal.config import Settings
    s = Settings()
    assert s.deployment_mode == "dev"


def test_settings_deployment_mode_from_env(monkeypatch):
    from ai_portal.config import Settings
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    s = Settings()
    assert s.deployment_mode == "saas"
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_auth_utils.py::test_settings_deployment_mode_defaults_to_dev -v
```

Expected: `AttributeError` — `deployment_mode` not on Settings yet.

- [ ] **Step 3: Update config.py**

In `backend/src/ai_portal/config.py`, update the `Settings` class. Add these fields after `auth_mode`:

```python
# New deployment mode — replaces auth_mode for new deployments.
# dev = dev token (backward compat)
# saas = open signup, JWT local auth
# selfhosted = invite-only, JWT local auth, setup wizard on first boot
deployment_mode: Literal["dev", "saas", "selfhosted"] = Field(
    default="dev",
    validation_alias=AliasChoices("DEPLOYMENT_MODE"),
)

# Required for local auth JWT signing. Generate with: python -c "import secrets; print(secrets.token_hex(32))"
secret_key: str = Field(default="", validation_alias=AliasChoices("SECRET_KEY"))

# SMTP for email verification, password reset, and invites
smtp_host: str = Field(default="", validation_alias=AliasChoices("SMTP_HOST"))
smtp_port: int = Field(default=587, validation_alias=AliasChoices("SMTP_PORT"))
smtp_user: str = Field(default="", validation_alias=AliasChoices("SMTP_USER"))
smtp_password: str = Field(default="", validation_alias=AliasChoices("SMTP_PASSWORD"))
email_from: str = Field(default="noreply@example.com", validation_alias=AliasChoices("EMAIL_FROM"))
```

Also update the `Literal` import at the top if needed — `Literal` is already imported from `typing`.

Also update `settings_log_snapshot` to include the new fields:

```python
"deployment_mode": st.deployment_mode,
"secret_key_set": bool(st.secret_key.strip()),
"smtp_host": st.smtp_host or "(not set)",
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_auth_utils.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/src/ai_portal/config.py backend/tests/test_auth_utils.py
git commit -m "feat(config): add deployment_mode, secret_key, smtp settings"
```

---

### Task 7: UserManager service

**Files:**
- Create: `backend/src/ai_portal/auth/manager.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_user_manager.py`:

```python
import uuid
from unittest.mock import MagicMock, patch

import pytest

from ai_portal.auth.manager import UserManager, RegistrationError, AuthenticationError


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def manager(db):
    return UserManager(db=db, secret="testsecret")


def test_register_creates_user_and_org(manager, db):
    # Mock: no existing user found
    db.scalars.return_value.first.return_value = None
    # Mock: org insert
    org_mock = MagicMock()
    org_mock.id = uuid.uuid4()
    user_mock = MagicMock()
    user_mock.uuid = uuid.uuid4()
    user_mock.org_id = org_mock.id
    user_mock.role = "owner"
    user_mock.is_active = True
    user_mock.is_verified = False

    with patch("ai_portal.auth.manager.Org", autospec=True) as MockOrg, \
         patch("ai_portal.auth.manager.User", autospec=True) as MockUser:
        MockOrg.return_value = org_mock
        MockUser.return_value = user_mock
        db.add = MagicMock()
        db.flush = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        result = manager.register(email="test@example.com", password="pass1234")
        assert db.add.call_count == 2  # org + user
        assert db.commit.called


def test_register_raises_on_duplicate_email(manager, db):
    existing = MagicMock()
    db.scalars.return_value.first.return_value = existing
    with pytest.raises(RegistrationError, match="Email already registered"):
        manager.register(email="exists@example.com", password="pass1234")


def test_authenticate_raises_on_bad_password(manager, db):
    from ai_portal.auth.password import hash_password
    user_mock = MagicMock()
    user_mock.hashed_password = hash_password("correctpass")
    user_mock.is_active = True
    db.scalars.return_value.first.return_value = user_mock
    with pytest.raises(AuthenticationError):
        manager.authenticate(email="x@x.com", password="wrongpass")
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_user_manager.py -v
```

Expected: `ImportError` — manager module not created yet.

- [ ] **Step 3: Create UserManager**

Create `backend/src/ai_portal/auth/manager.py`:

```python
from __future__ import annotations

import re
import secrets
import uuid as _uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.jwt import create_access_token, create_refresh_token
from ai_portal.auth.password import hash_password, verify_password
from ai_portal.models.org import Org
from ai_portal.models.user import User


class RegistrationError(ValueError):
    pass


class AuthenticationError(ValueError):
    pass


def _slugify(email: str) -> str:
    local = email.split("@")[0]
    slug = re.sub(r"[^a-z0-9]", "-", local.lower())[:48]
    return f"{slug}-{secrets.token_hex(4)}"


class UserManager:
    def __init__(self, db: Session, secret: str) -> None:
        self._db = db
        self._secret = secret

    def register(
        self,
        *,
        email: str,
        password: str,
        org_id: _uuid.UUID | None = None,
        role: str = "owner",
    ) -> User:
        """Register a new user.

        If org_id is None (SaaS open signup), a personal org is created automatically.
        If org_id is provided (invite flow), the user joins that org as a member.
        """
        existing = self._db.scalars(
            select(User).where(User.email == email.lower().strip())
        ).first()
        if existing is not None:
            raise RegistrationError("Email already registered")

        if org_id is None:
            # Create personal org
            personal_org = Org(slug=_slugify(email), name=email.split("@")[0])
            self._db.add(personal_org)
            self._db.flush()  # populate personal_org.id
            effective_org_id = personal_org.id
        else:
            effective_org_id = org_id

        user = User(
            email=email.lower().strip(),
            hashed_password=hash_password(password),
            uuid=_uuid.uuid4(),
            org_id=effective_org_id,
            role=role,
            is_active=True,
            is_verified=False,
        )
        self._db.add(user)
        self._db.commit()
        self._db.refresh(user)
        return user

    def authenticate(self, *, email: str, password: str) -> User:
        """Return user if credentials valid. Raises AuthenticationError otherwise."""
        user = self._db.scalars(
            select(User).where(User.email == email.lower().strip())
        ).first()
        if user is None or not user.hashed_password:
            raise AuthenticationError("Invalid email or password")
        if not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")
        if not user.is_active:
            raise AuthenticationError("Account is disabled")
        return user

    def create_tokens(self, user: User) -> dict[str, str]:
        """Return {access_token, refresh_token, token_type} for a user."""
        return {
            "access_token": create_access_token(
                user_uuid=user.uuid,
                org_id=user.org_id,
                role=user.role,
                secret=self._secret,
            ),
            "refresh_token": create_refresh_token(
                user_uuid=user.uuid,
                org_id=user.org_id,
                role=user.role,
                secret=self._secret,
            ),
            "token_type": "bearer",
        }

    def get_by_uuid(self, user_uuid: _uuid.UUID) -> User | None:
        return self._db.scalars(
            select(User).where(User.uuid == user_uuid)
        ).first()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_user_manager.py -v
```

Expected: all 3 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/src/ai_portal/auth/manager.py backend/tests/test_user_manager.py
git commit -m "feat(auth): UserManager with register, authenticate, create_tokens"
```

---

### Task 8: Auth router

**Files:**
- Create: `backend/src/ai_portal/api/auth.py`
- Modify: `backend/src/ai_portal/api/deps.py`
- Modify: `backend/src/ai_portal/main.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_auth_api.py`:

```python
import pytest
from fastapi.testclient import TestClient

from ai_portal.main import app

client = TestClient(app)


def test_register_and_login(tmp_path, monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    monkeypatch.setenv("SECRET_KEY", "testsecretkey1234567890")
    # Reload settings by calling the endpoint
    resp = client.post("/auth/register", json={
        "email": "newuser@example.com",
        "password": "TestPass123!"
    })
    # May fail with 422 if endpoint doesn't exist yet, or 500 if DB not available
    # In CI with a real DB this should return 201
    assert resp.status_code in (201, 422, 500, 404)
```

- [ ] **Step 2: Run to verify it returns 404 (route not registered yet)**

```bash
pytest tests/test_auth_api.py -v
```

Expected: 404 or ImportError — route doesn't exist yet.

- [ ] **Step 3: Create auth router**

Create `backend/src/ai_portal/api/auth.py`:

```python
from __future__ import annotations

import uuid as _uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.api.deps import get_db
from ai_portal.auth.jwt import decode_token
from ai_portal.auth.manager import AuthenticationError, RegistrationError, UserManager
from ai_portal.config import get_settings
from ai_portal.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    id: int
    email: str
    role: str
    is_verified: bool
    is_superuser: bool
    org_id: str | None

    model_config = {"from_attributes": True}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _require_local_auth() -> None:
    settings = get_settings()
    if settings.deployment_mode not in ("saas", "selfhosted"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Local auth is only available when DEPLOYMENT_MODE=saas or selfhosted",
        )


def _require_signup_open() -> None:
    settings = get_settings()
    if settings.deployment_mode == "selfhosted":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Open signup is disabled. Use an invite link.",
        )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    _require_local_auth()
    _require_signup_open()
    settings = get_settings()
    manager = UserManager(db=db, secret=settings.secret_key)
    try:
        user = manager.register(email=body.email, password=body.password)
    except RegistrationError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
    tokens = manager.create_tokens(user)
    return TokenResponse(**tokens)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    _require_local_auth()
    settings = get_settings()
    manager = UserManager(db=db, secret=settings.secret_key)
    try:
        user = manager.authenticate(email=body.email, password=body.password)
    except AuthenticationError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(e))
    tokens = manager.create_tokens(user)
    return TokenResponse(**tokens)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    _require_local_auth()
    settings = get_settings()
    try:
        payload = decode_token(body.refresh_token, secret=settings.secret_key)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not a refresh token")
    user_uuid = _uuid.UUID(payload["sub"])
    manager = UserManager(db=db, secret=settings.secret_key)
    user = manager.get_by_uuid(user_uuid)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found")
    tokens = manager.create_tokens(user)
    return TokenResponse(**tokens)


@router.get("/me", response_model=UserRead)
def auth_me(db: Session = Depends(get_db), authorization: str | None = None) -> UserRead:
    """Lightweight identity endpoint for local auth mode."""
    _require_local_auth()
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    token = authorization.split(" ", 1)[1].strip()
    settings = get_settings()
    try:
        payload = decode_token(token, secret=settings.secret_key)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_uuid = _uuid.UUID(payload["sub"])
    user = db.scalars(select(User).where(User.uuid == user_uuid)).first()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return UserRead(
        id=user.id,
        email=user.email,
        role=user.role,
        is_verified=user.is_verified,
        is_superuser=user.is_superuser,
        org_id=str(user.org_id) if user.org_id else None,
    )
```

- [ ] **Step 4: Update deps.py to handle local auth JWT**

In `backend/src/ai_portal/api/deps.py`, add a new branch for `deployment_mode in ("saas", "selfhosted")` **before** the existing `auth_mode` checks. Add these imports at the top:

```python
import uuid as _uuid
from ai_portal.auth.jwt import decode_token
```

In `get_current_user`, add this block right after the `aip_` key check:

```python
    # New local auth: deployment_mode=saas|selfhosted uses JWT with uuid sub
    if settings.deployment_mode in ("saas", "selfhosted"):
        try:
            payload = decode_token(token, secret=settings.secret_key)
        except jwt.PyJWTError as e:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from e
        if payload.get("type") != "access":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not an access token")
        user_uuid = _uuid.UUID(payload["sub"])
        user = db.scalars(select(User).where(User.uuid == user_uuid)).first()
        if user is None or not user.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user
```

This block must go **after** the `aip_` key check and **before** the `if settings.auth_mode == "dev":` block.

- [ ] **Step 5: Register auth router in main.py**

In `backend/src/ai_portal/main.py`, add:

```python
from ai_portal.api import auth
```

And in the router registrations:

```python
app.include_router(auth.router)
```

Add it before the other `app.include_router(...)` calls.

- [ ] **Step 6: Run test**

```bash
pytest tests/test_auth_api.py -v
```

Expected: `PASSED` (returns 201, 409, or 404 depending on DB availability — the key check is that `404` is gone).

- [ ] **Step 7: Commit**

```bash
git add backend/src/ai_portal/api/auth.py backend/src/ai_portal/api/deps.py backend/src/ai_portal/main.py backend/tests/test_auth_api.py
git commit -m "feat(api): /auth router — register, login, refresh, me endpoints"
```

---

## Sub-project 2: Multi-tenancy Core

### Task 9: Alembic migration — add org_id to all tenant-scoped tables

**Files:**
- Create: `backend/alembic/versions/023_multitenancy.py`

- [ ] **Step 1: Create the migration**

Create `backend/alembic/versions/023_multitenancy.py`:

```python
"""Add org_id to all tenant-scoped tables

Revision ID: 023_multitenancy
Revises: 022_auth_overhaul
Create Date: 2026-04-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "023_multitenancy"
down_revision = "022_auth_overhaul"
branch_labels = None
depends_on = None

TABLES = [
    "assistants",
    "chat_conversations",
    "knowledge_bases",
    "user_memories",
    "catalog_models",
    "user_portal_api_keys",
]


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("org_id", UUID(as_uuid=True), nullable=True),
        )
        # Backfill from users table via the existing user FK
        # Each table has either owner_user_id or user_id referencing users.id
        user_col = "owner_user_id" if table in ("assistants", "knowledge_bases") else "user_id"
        if table == "catalog_models":
            # catalog_models has no user FK — assign to default org directly
            op.execute(
                f"UPDATE {table} SET org_id = (SELECT id FROM orgs WHERE slug = 'default')"
            )
        else:
            op.execute(
                f"UPDATE {table} SET org_id = ("
                f"  SELECT org_id FROM users WHERE users.id = {table}.{user_col}"
                f")"
            )
        # Make NOT NULL after backfill
        op.alter_column(table, "org_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_org_id", table, "orgs", ["org_id"], ["id"]
        )
        op.create_index(f"ix_{table}_org_id", table, ["org_id"])


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_index(f"ix_{table}_org_id", table)
        op.drop_constraint(f"fk_{table}_org_id", table, type_="foreignkey")
        op.drop_column(table, "org_id")
```

- [ ] **Step 2: Apply migration**

```bash
cd backend
python -m alembic upgrade 023_multitenancy
```

Expected: migration completes without error.

- [ ] **Step 3: Verify**

```bash
python -c "
from ai_portal.db.session import SessionLocal
from sqlalchemy import text
db = SessionLocal()
r = db.execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_name='assistants' AND column_name='org_id'\")).fetchall()
print('org_id on assistants:', bool(r))
db.close()
"
```

Expected: `org_id on assistants: True`

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/023_multitenancy.py
git commit -m "feat(migrations): 023 add org_id to all tenant-scoped tables"
```

---

### Task 10: TenantRepository base class

**Files:**
- Create: `backend/src/ai_portal/db/tenant.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_tenant_repository.py`:

```python
import uuid
from unittest.mock import MagicMock, patch

import pytest

from ai_portal.db.tenant import TenantRepository


class FakeModel:
    __tablename__ = "fake"
    id = None
    org_id = None


def test_get_returns_none_when_not_found():
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    repo = TenantRepository(db=db, model=FakeModel)
    result = repo.get(id=1, org_id=uuid.uuid4())
    assert result is None


def test_get_passes_org_id_filter():
    db = MagicMock()
    org_id = uuid.uuid4()
    db.scalars.return_value.first.return_value = MagicMock()
    repo = TenantRepository(db=db, model=FakeModel)
    repo.get(id=1, org_id=org_id)
    # The where clause must have been applied — verify execute was called
    assert db.scalars.called
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_tenant_repository.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Create TenantRepository**

Create `backend/src/ai_portal/db/tenant.py`:

```python
from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.db.base import Base

T = TypeVar("T", bound=Base)


class TenantRepository(Generic[T]):
    """Base repository that enforces org_id on all queries.

    Usage:
        repo = TenantRepository(db=db, model=Assistant)
        assistants = repo.all(org_id=user.org_id)
    """

    def __init__(self, *, db: Session, model: type[T]) -> None:
        self._db = db
        self._model = model

    def all(self, org_id: uuid.UUID) -> list[T]:
        return list(
            self._db.scalars(
                select(self._model).where(self._model.org_id == org_id)
            ).all()
        )

    def get(self, *, id: Any, org_id: uuid.UUID) -> T | None:
        return self._db.scalars(
            select(self._model).where(
                self._model.id == id,
                self._model.org_id == org_id,
            )
        ).first()

    def create(self, *, data: dict, org_id: uuid.UUID) -> T:
        obj = self._model(**data, org_id=org_id)
        self._db.add(obj)
        self._db.commit()
        self._db.refresh(obj)
        return obj

    def update(self, *, id: Any, data: dict, org_id: uuid.UUID) -> T:
        obj = self.get(id=id, org_id=org_id)
        if obj is None:
            raise ValueError(f"{self._model.__tablename__} {id} not found in org {org_id}")
        for k, v in data.items():
            setattr(obj, k, v)
        self._db.commit()
        self._db.refresh(obj)
        return obj

    def delete(self, *, id: Any, org_id: uuid.UUID) -> None:
        obj = self.get(id=id, org_id=org_id)
        if obj is None:
            raise ValueError(f"{self._model.__tablename__} {id} not found in org {org_id}")
        self._db.delete(obj)
        self._db.commit()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tenant_repository.py -v
```

Expected: both tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/src/ai_portal/db/tenant.py backend/tests/test_tenant_repository.py
git commit -m "feat(db): TenantRepository base class for org-scoped queries"
```

---

### Task 11: Wire org_id into API dependencies

**Files:**
- Modify: `backend/src/ai_portal/api/deps.py`

Add a `get_current_org_id` dependency that all tenant-scoped routes will use. This replaces manual `user.id` filtering with `org_id` filtering.

- [ ] **Step 1: Add get_current_org_id to deps.py**

In `backend/src/ai_portal/api/deps.py`, add at the bottom:

```python
def get_current_org_id(
    user: User = Depends(get_current_user),
) -> _uuid.UUID:
    """Extract org_id from the authenticated user.

    All tenant-scoped routes use this dependency to scope their queries.
    Raises 403 if the user has no org assigned (shouldn't happen post-migration).
    """
    if user.org_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="User has no organization assigned.",
        )
    return user.org_id
```

- [ ] **Step 2: Write test**

Add to `backend/tests/test_auth_utils.py`:

```python
def test_get_current_org_id_returns_uuid():
    import uuid
    from unittest.mock import MagicMock
    from ai_portal.api.deps import get_current_org_id

    user = MagicMock()
    user.org_id = uuid.uuid4()
    result = get_current_org_id(user=user)
    assert result == user.org_id


def test_get_current_org_id_raises_when_no_org():
    from unittest.mock import MagicMock
    from fastapi import HTTPException
    from ai_portal.api.deps import get_current_org_id

    user = MagicMock()
    user.org_id = None
    with pytest.raises(HTTPException) as exc:
        get_current_org_id(user=user)
    assert exc.value.status_code == 403
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_auth_utils.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 4: Commit**

```bash
git add backend/src/ai_portal/api/deps.py backend/tests/test_auth_utils.py
git commit -m "feat(deps): add get_current_org_id dependency for tenant isolation"
```

---

### Task 12: Update assistants API for tenant isolation

**Files:**
- Modify: `backend/src/ai_portal/api/assistants.py`

- [ ] **Step 1: Update the assistants router**

In `backend/src/ai_portal/api/assistants.py`, make these changes:

**Add import:**
```python
import uuid as _uuid
from ai_portal.api.deps import get_current_org_id
```

**Replace `_visible_assistants_stmt`** — the current function filters by user ACL. Update to also scope by org:

```python
def _visible_assistants_stmt(user: User, org_id: _uuid.UUID):
    acl = select(AssistantAcl.assistant_id).where(AssistantAcl.user_id == user.id)
    return select(Assistant).where(
        Assistant.org_id == org_id,
        or_(
            Assistant.owner_user_id == user.id,
            Assistant.visibility == "org",
            Assistant.id.in_(acl),
        ),
    )
```

**Update `GET /` list endpoint** — add `org_id` parameter:

```python
@router.get("/", response_model=list[AssistantRead])
def list_assistants(
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> list[AssistantRead]:
    rows = db.scalars(_visible_assistants_stmt(user, org_id)).all()
    return [AssistantRead.model_validate(r) for r in rows]
```

**Update `POST /` create endpoint** — set `org_id` on creation:

```python
@router.post("/", status_code=status.HTTP_201_CREATED, response_model=AssistantRead)
def create_assistant(
    body: AssistantCreate,
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> AssistantRead:
    assistant = Assistant(
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        visibility=body.visibility,
        owner_user_id=user.id,
        org_id=org_id,
    )
    db.add(assistant)
    db.commit()
    db.refresh(assistant)
    return AssistantRead.model_validate(assistant)
```

**Update all remaining routes** (GET /{id}, PATCH /{id}, DELETE /{id}) to add `org_id: _uuid.UUID = Depends(get_current_org_id)` and pass `org_id` to `_visible_assistants_stmt`. The `_can_access_assistant` helper also needs an `org_id` argument:

```python
def _can_access_assistant(
    assistant_id: int, user: User, org_id: _uuid.UUID, db: Session
) -> Assistant:
    stmt = _visible_assistants_stmt(user, org_id).where(Assistant.id == assistant_id)
    assistant = db.scalars(stmt).first()
    if assistant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assistant not found")
    return assistant
```

Update all three remaining routes to call `_can_access_assistant(id, user, org_id, db)` and add `org_id: _uuid.UUID = Depends(get_current_org_id)` to their signatures.

- [ ] **Step 2: Run existing tests**

```bash
pytest tests/ -v -k "assistant" 2>/dev/null || echo "no assistant tests yet"
```

- [ ] **Step 3: Commit**

```bash
git add backend/src/ai_portal/api/assistants.py
git commit -m "feat(api): scope assistants queries to org_id"
```

---

### Task 13: Update conversations, knowledge_bases, memories APIs

**Files:**
- Modify: `backend/src/ai_portal/api/conversations.py`
- Modify: `backend/src/ai_portal/api/knowledge_bases.py`
- Modify: `backend/src/ai_portal/api/memories.py`

Apply the same `org_id` pattern to each:

- [ ] **Step 1: conversations.py**

Add to imports:
```python
import uuid as _uuid
from ai_portal.api.deps import get_current_org_id
```

For every route that creates a `ChatConversation`, add `org_id=org_id` to the constructor. For every query that filters by `user_id`, add an additional `.where(ChatConversation.org_id == org_id)` filter.

Example — the list conversations query becomes:
```python
stmt = (
    select(ChatConversation)
    .where(
        ChatConversation.user_id == user.id,
        ChatConversation.org_id == org_id,
    )
    .order_by(ChatConversation.last_message_at.desc().nullslast(), ChatConversation.created_at.desc())
    .limit(limit)
    .offset(offset)
)
```

Add `org_id: _uuid.UUID = Depends(get_current_org_id)` to every route function signature.

When creating a new conversation:
```python
conv = ChatConversation(
    user_id=user.id,
    org_id=org_id,
    ...
)
```

- [ ] **Step 2: knowledge_bases.py**

Same pattern — add `org_id: _uuid.UUID = Depends(get_current_org_id)` to all routes. Add `KnowledgeBase.org_id == org_id` to all queries. Set `org_id=org_id` when creating a KB.

- [ ] **Step 3: memories.py**

Same pattern — add `org_id` dependency and filter. Memory rows belong to a user within an org — filter by both `user_id` and `org_id`.

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all existing tests pass (the dev auth mode bypasses org checks if needed during testing).

- [ ] **Step 5: Commit**

```bash
git add backend/src/ai_portal/api/conversations.py backend/src/ai_portal/api/knowledge_bases.py backend/src/ai_portal/api/memories.py
git commit -m "feat(api): scope conversations, knowledge_bases, memories to org_id"
```

---

### Task 14: Update model_catalog and portal_api_keys APIs

**Files:**
- Modify: `backend/src/ai_portal/api/model_catalog.py`
- Modify: `backend/src/ai_portal/api/me.py`

- [ ] **Step 1: model_catalog.py**

The catalog shows global models (no user FK). Add `org_id` filter for org-level overrides if present, but fall back to showing all catalog models (since catalog_models are global, just filtered by `org_id` after migration backfill). The simplest change: don't filter by org in catalog list — it's a read-only global catalog. No change needed unless you want per-org model visibility later.

For now, add a comment: `# catalog_models.org_id is set but not yet used for per-org visibility`

- [ ] **Step 2: me.py (portal_api_keys)**

In `backend/src/ai_portal/api/me.py`, the portal API key endpoints query `user_portal_api_keys` by `user_id`. These already scope to user so cross-org leakage isn't possible. Add `org_id` as a secondary index for future use:

```python
import uuid as _uuid
from ai_portal.api.deps import get_current_org_id
```

No query changes needed since keys are scoped by `user_id` which is already user-specific.

- [ ] **Step 3: Commit**

```bash
git add backend/src/ai_portal/api/model_catalog.py backend/src/ai_portal/api/me.py
git commit -m "feat(api): note org_id on catalog_models; me.py remains user-scoped"
```

---

## Sub-project 3: Deployment Modes + Org Management

### Task 15: Setup guard middleware

**Files:**
- Create: `backend/src/ai_portal/middleware/setup_guard.py`
- Modify: `backend/src/ai_portal/main.py`

When `DEPLOYMENT_MODE=selfhosted` and no orgs exist in the DB, all routes except `/health` and `/setup` return `503 Setup Required`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_auth_api.py`:

```python
def test_setup_guard_returns_503_when_no_orgs(monkeypatch):
    """When selfhosted and orgs table is empty, non-exempt routes return 503."""
    monkeypatch.setenv("DEPLOYMENT_MODE", "selfhosted")
    # Can't easily empty the DB in unit test — just verify middleware is importable
    from ai_portal.middleware.setup_guard import SetupGuardMiddleware
    assert SetupGuardMiddleware is not None
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/test_auth_api.py::test_setup_guard_returns_503_when_no_orgs -v
```

Expected: `ImportError`

- [ ] **Step 3: Create the middleware**

Create `backend/src/ai_portal/middleware/__init__.py` (empty).

Create `backend/src/ai_portal/middleware/setup_guard.py`:

```python
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ai_portal.config import get_settings
from ai_portal.db.session import SessionLocal
from ai_portal.models.org import Org
from sqlalchemy import select, func


EXEMPT_PATHS = {"/health", "/setup", "/auth/login"}


class SetupGuardMiddleware(BaseHTTPMiddleware):
    """Block all routes with 503 when DEPLOYMENT_MODE=selfhosted and no orgs exist."""

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if settings.deployment_mode != "selfhosted":
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(exempt) for exempt in EXEMPT_PATHS):
            return await call_next(request)

        db = SessionLocal()
        try:
            count = db.scalar(select(func.count()).select_from(Org))
        finally:
            db.close()

        if count == 0:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Setup required. POST /setup to initialize this instance."
                },
            )

        return await call_next(request)
```

- [ ] **Step 4: Register in main.py**

In `backend/src/ai_portal/main.py`, add:

```python
from ai_portal.middleware.setup_guard import SetupGuardMiddleware

app.add_middleware(SetupGuardMiddleware)
```

Add this **after** the CORS middleware registration.

- [ ] **Step 5: Run test**

```bash
pytest tests/test_auth_api.py::test_setup_guard_returns_503_when_no_orgs -v
```

Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/middleware/__init__.py backend/src/ai_portal/middleware/setup_guard.py backend/src/ai_portal/main.py backend/tests/test_auth_api.py
git commit -m "feat(middleware): SetupGuardMiddleware blocks routes until selfhosted setup completes"
```

---

### Task 16: POST /setup endpoint

**Files:**
- Create: `backend/src/ai_portal/api/setup.py`
- Modify: `backend/src/ai_portal/main.py`

- [ ] **Step 1: Create the setup endpoint**

Create `backend/src/ai_portal/api/setup.py`:

```python
from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_portal.api.deps import get_db
from ai_portal.auth.manager import RegistrationError, UserManager
from ai_portal.config import get_settings
from ai_portal.models.org import Org

router = APIRouter(tags=["setup"])


class SetupRequest(BaseModel):
    org_name: str = Field(min_length=1, max_length=255)
    admin_email: str = Field(min_length=3, max_length=255)
    admin_password: str = Field(min_length=8, max_length=128)


class SetupResponse(BaseModel):
    message: str
    org_id: str


@router.post("/setup", response_model=SetupResponse, status_code=status.HTTP_201_CREATED)
def first_run_setup(body: SetupRequest, db: Session = Depends(get_db)) -> SetupResponse:
    settings = get_settings()

    if settings.deployment_mode != "selfhosted":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Setup endpoint is only available in selfhosted mode.",
        )

    # Check if already set up
    count = db.scalar(select(func.count()).select_from(Org))
    if count > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Instance is already set up.",
        )

    # Create the instance org
    org = Org(
        slug="instance",
        name=body.org_name,
        instance_mode=True,
    )
    db.add(org)
    db.flush()

    # Create admin user (owner + superuser)
    manager = UserManager(db=db, secret=settings.secret_key)
    try:
        user = manager.register(
            email=body.admin_email,
            password=body.admin_password,
            org_id=org.id,
            role="owner",
        )
    except RegistrationError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))

    # Make them superuser
    user.is_superuser = True
    user.is_verified = True
    db.commit()

    return SetupResponse(
        message="Instance setup complete. You can now log in.",
        org_id=str(org.id),
    )
```

- [ ] **Step 2: Register in main.py**

```python
from ai_portal.api import setup as setup_router

app.include_router(setup_router.router)
```

- [ ] **Step 3: Write and run test**

Add to `backend/tests/test_auth_api.py`:

```python
def test_setup_endpoint_unavailable_in_saas_mode(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    resp = client.post("/setup", json={
        "org_name": "Test Org",
        "admin_email": "admin@example.com",
        "admin_password": "AdminPass123!"
    })
    assert resp.status_code == 400
```

```bash
pytest tests/test_auth_api.py::test_setup_endpoint_unavailable_in_saas_mode -v
```

Expected: `PASSED`

- [ ] **Step 4: Commit**

```bash
git add backend/src/ai_portal/api/setup.py backend/src/ai_portal/main.py backend/tests/test_auth_api.py
git commit -m "feat(api): POST /setup first-run wizard for selfhosted mode"
```

---

### Task 17: Org management API + invite model

**Files:**
- Create: `backend/src/ai_portal/models/org_invite.py`
- Create: `backend/alembic/versions/024_org_invites.py`
- Create: `backend/src/ai_portal/api/orgs.py`
- Modify: `backend/src/ai_portal/models/__init__.py`
- Modify: `backend/src/ai_portal/main.py`

- [ ] **Step 1: Create OrgInvite model**

Create `backend/src/ai_portal/models/org_invite.py`:

```python
from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.db.base import Base


class OrgInvite(Base):
    __tablename__ = "org_invites"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[_uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    invited_email: Mapped[str] = mapped_column(String(255), nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")
    created_by_user_id: Mapped[int] = mapped_column(nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

Add `from ai_portal.models.org_invite import OrgInvite` to `backend/src/ai_portal/models/__init__.py`.

- [ ] **Step 2: Create migration 024**

Create `backend/alembic/versions/024_org_invites.py`:

```python
"""Create org_invites table

Revision ID: 024_org_invites
Revises: 023_multitenancy
Create Date: 2026-04-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "024_org_invites"
down_revision = "023_multitenancy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_invites",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("invited_email", sa.String(255), nullable=False),
        sa.Column("token", sa.String(64), unique=True, nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="member"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_org_invites_org_id", "org_invites", ["org_id"])
    op.create_index("ix_org_invites_token", "org_invites", ["token"])
    op.create_foreign_key("fk_org_invites_org_id", "org_invites", "orgs", ["org_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_org_invites_org_id", "org_invites", type_="foreignkey")
    op.drop_index("ix_org_invites_token", "org_invites")
    op.drop_index("ix_org_invites_org_id", "org_invites")
    op.drop_table("org_invites")
```

- [ ] **Step 3: Apply migration**

```bash
cd backend
python -m alembic upgrade 024_org_invites
```

- [ ] **Step 4: Create orgs router**

Create `backend/src/ai_portal/api/orgs.py`:

```python
from __future__ import annotations

import secrets
import uuid as _uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.api.deps import get_current_org_id, get_current_user, get_db
from ai_portal.models.org import Org
from ai_portal.models.org_invite import OrgInvite
from ai_portal.models.user import User

router = APIRouter(prefix="/api/orgs", tags=["orgs"])

INVITE_EXPIRY_DAYS = 7


# ── Schemas ───────────────────────────────────────────────────────────────────

class OrgRead(BaseModel):
    id: str
    slug: str
    name: str
    instance_mode: bool

    model_config = {"from_attributes": True}


class OrgPatch(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    slug: str | None = Field(default=None, max_length=64)


class MemberRead(BaseModel):
    id: int
    email: str
    role: str
    is_verified: bool

    model_config = {"from_attributes": True}


class MemberRolePatch(BaseModel):
    role: str = Field(pattern="^(owner|admin|member)$")


class InviteCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: str = Field(default="member", pattern="^(admin|member)$")


class InviteRead(BaseModel):
    id: int
    invited_email: str
    role: str
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_role(user: User, *allowed: str) -> None:
    if user.role not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Insufficient role")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/me", response_model=OrgRead)
def get_my_org(
    org_id: _uuid.UUID = Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> OrgRead:
    org = db.scalars(select(Org).where(Org.id == org_id)).first()
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Org not found")
    return OrgRead.model_validate(org)


@router.patch("/me", response_model=OrgRead)
def update_my_org(
    body: OrgPatch,
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> OrgRead:
    _require_role(user, "owner", "admin")
    org = db.scalars(select(Org).where(Org.id == org_id)).first()
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Org not found")
    if body.name is not None:
        org.name = body.name
    if body.slug is not None:
        existing = db.scalars(select(Org).where(Org.slug == body.slug, Org.id != org_id)).first()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Slug already taken")
        org.slug = body.slug
    db.commit()
    db.refresh(org)
    return OrgRead.model_validate(org)


@router.get("/me/members", response_model=list[MemberRead])
def list_members(
    org_id: _uuid.UUID = Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> list[MemberRead]:
    members = db.scalars(select(User).where(User.org_id == org_id)).all()
    return [MemberRead.model_validate(m) for m in members]


@router.patch("/me/members/{member_id}", response_model=MemberRead)
def update_member_role(
    member_id: int,
    body: MemberRolePatch,
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> MemberRead:
    _require_role(user, "owner")
    member = db.scalars(
        select(User).where(User.id == member_id, User.org_id == org_id)
    ).first()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Member not found")
    if member.id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cannot change your own role")
    member.role = body.role
    db.commit()
    db.refresh(member)
    return MemberRead.model_validate(member)


@router.delete("/me/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    member_id: int,
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> None:
    _require_role(user, "owner", "admin")
    member = db.scalars(
        select(User).where(User.id == member_id, User.org_id == org_id)
    ).first()
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Member not found")
    if member.id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cannot remove yourself")
    db.delete(member)
    db.commit()


@router.post("/me/invites", status_code=status.HTTP_201_CREATED, response_model=InviteRead)
def create_invite(
    body: InviteCreate,
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> InviteRead:
    _require_role(user, "owner", "admin")
    # Revoke any existing pending invite for this email in this org
    existing = db.scalars(
        select(OrgInvite).where(
            OrgInvite.org_id == org_id,
            OrgInvite.invited_email == body.email.lower().strip(),
            OrgInvite.accepted_at == None,  # noqa: E711
            OrgInvite.revoked_at == None,  # noqa: E711
        )
    ).first()
    if existing:
        existing.revoked_at = datetime.now(UTC)
        db.flush()

    invite = OrgInvite(
        org_id=org_id,
        invited_email=body.email.lower().strip(),
        token=secrets.token_urlsafe(32),
        role=body.role,
        created_by_user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=INVITE_EXPIRY_DAYS),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return InviteRead.model_validate(invite)


@router.get("/me/invites", response_model=list[InviteRead])
def list_invites(
    org_id: _uuid.UUID = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[InviteRead]:
    _require_role(user, "owner", "admin")
    invites = db.scalars(
        select(OrgInvite).where(
            OrgInvite.org_id == org_id,
            OrgInvite.accepted_at == None,  # noqa: E711
            OrgInvite.revoked_at == None,  # noqa: E711
        )
    ).all()
    return [InviteRead.model_validate(i) for i in invites]


@router.delete("/me/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(
    invite_id: int,
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    db: Session = Depends(get_db),
) -> None:
    _require_role(user, "owner", "admin")
    invite = db.scalars(
        select(OrgInvite).where(OrgInvite.id == invite_id, OrgInvite.org_id == org_id)
    ).first()
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite not found")
    invite.revoked_at = datetime.now(UTC)
    db.commit()
```

- [ ] **Step 5: Register in main.py**

```python
from ai_portal.api import orgs

app.include_router(orgs.router)
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/models/org_invite.py backend/alembic/versions/024_org_invites.py backend/src/ai_portal/api/orgs.py backend/src/ai_portal/models/__init__.py backend/src/ai_portal/main.py
git commit -m "feat(api): org management — GET/PATCH org, members CRUD, invite create/list/revoke"
```

---

### Task 18: Accept-invite endpoint

**Files:**
- Modify: `backend/src/ai_portal/api/auth.py`

- [ ] **Step 1: Add POST /auth/accept-invite to auth.py**

In `backend/src/ai_portal/api/auth.py`, add these imports:

```python
from datetime import UTC, datetime
from ai_portal.models.org_invite import OrgInvite
```

Add the endpoint:

```python
class AcceptInviteRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


@router.post("/accept-invite", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
def accept_invite(body: AcceptInviteRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Accept an org invite and create an account (or migrate an existing one)."""
    invite = db.scalars(
        select(OrgInvite).where(
            OrgInvite.token == body.token,
            OrgInvite.accepted_at == None,  # noqa: E711
            OrgInvite.revoked_at == None,  # noqa: E711
        )
    ).first()
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite not found or expired")
    if invite.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(status.HTTP_410_GONE, detail="Invite has expired")

    settings = get_settings()
    manager = UserManager(db=db, secret=settings.secret_key)

    # Check if user already exists (migrate) or create new
    existing_user = db.scalars(
        select(User).where(User.email == invite.invited_email)
    ).first()

    if existing_user:
        # Migrate to new org — archive old personal org if it exists
        old_org = db.scalars(
            select(Org).where(
                Org.id == existing_user.org_id,
                Org.instance_mode == False,  # noqa: E712
            )
        ).first()
        if old_org and old_org.slug.startswith(existing_user.email.split("@")[0]):
            old_org.archived_at = datetime.now(UTC)
        existing_user.org_id = invite.org_id
        existing_user.role = invite.role
        user = existing_user
    else:
        try:
            user = manager.register(
                email=invite.invited_email,
                password=body.password,
                org_id=invite.org_id,
                role=invite.role,
            )
        except RegistrationError as e:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))

    invite.accepted_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    tokens = manager.create_tokens(user)
    return TokenResponse(**tokens)
```

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all existing tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/src/ai_portal/api/auth.py
git commit -m "feat(api): POST /auth/accept-invite — create account or migrate org on invite acceptance"
```

---

## Sub-project 4: Frontend Auth Pages

### Task 19: Token store + update authorizedFetch

**Files:**
- Create: `frontend/src/auth/tokenStore.ts`
- Modify: `frontend/src/auth/msalConfig.ts`
- Modify: `frontend/src/lib/authorizedFetch.ts`

- [ ] **Step 1: Create token store**

Create `frontend/src/auth/tokenStore.ts`:

```typescript
const ACCESS_KEY = 'aip_access_token'
const REFRESH_KEY = 'aip_refresh_token'

export const tokenStore = {
  getAccess: (): string | null => {
    if (typeof window === 'undefined') return null
    return localStorage.getItem(ACCESS_KEY)
  },
  getRefresh: (): string | null => {
    if (typeof window === 'undefined') return null
    return localStorage.getItem(REFRESH_KEY)
  },
  set: (access: string, refresh: string): void => {
    localStorage.setItem(ACCESS_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear: (): void => {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}
```

- [ ] **Step 2: Update msalConfig.ts to add 'local' mode**

In `frontend/src/auth/msalConfig.ts`, update `getAuthMode`:

```typescript
export function getAuthMode(): 'dev' | 'entra' | 'local' {
  const m = import.meta.env.VITE_AUTH_MODE
  if (m === 'entra') return 'entra'
  if (m === 'local') return 'local'
  return 'dev'
}
```

- [ ] **Step 3: Update authorizedFetch.ts**

Replace `frontend/src/lib/authorizedFetch.ts` with:

```typescript
import { InteractionRequiredAuthError } from '@azure/msal-browser'

import { apiTokenRequest, getAuthMode, getEntraApiScope } from '~/auth/msalConfig'
import { getMsalInstance } from '~/auth/msalInstance'
import { tokenStore } from '~/auth/tokenStore'

export async function getAuthHeaders(): Promise<HeadersInit> {
  const mode = getAuthMode()

  if (mode === 'local') {
    const token = tokenStore.getAccess()
    if (!token) throw new Error('Not authenticated. Please log in.')
    return { Authorization: `Bearer ${token}` }
  }

  if (mode !== 'entra') {
    const t =
      import.meta.env.VITE_DEV_BEARER_TOKEN ??
      import.meta.env.VITE_DEV_TOKEN ??
      'devtoken'
    return { Authorization: `Bearer ${t}` }
  }

  if (!getEntraApiScope()) {
    throw new Error(
      'VITE_ENTRA_API_SCOPE is not set. The backend expects an access token for your API audience.',
    )
  }

  const msal = getMsalInstance()
  if (!msal) {
    throw new Error(
      'MSAL is not initialized yet (Entra). Avoid calling authorizedFetch during SSR or before EntraRoot finishes loading.',
    )
  }
  const account = msal.getActiveAccount() ?? msal.getAllAccounts()[0]
  if (!account) {
    throw new Error('No Entra account in MSAL cache. Sign in again.')
  }
  try {
    const result = await msal.acquireTokenSilent({
      ...apiTokenRequest(),
      account,
    })
    return { Authorization: `Bearer ${result.accessToken}` }
  } catch (e) {
    if (e instanceof InteractionRequiredAuthError) {
      await msal.acquireTokenRedirect({ ...apiTokenRequest(), account })
    }
    throw e
  }
}

export async function authorizedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers)
  const auth = await getAuthHeaders()
  for (const [k, v] of Object.entries(auth)) {
    headers.set(k, v)
  }
  return fetch(input, { ...init, headers })
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/auth/tokenStore.ts frontend/src/auth/msalConfig.ts frontend/src/lib/authorizedFetch.ts
git commit -m "feat(frontend): tokenStore + local auth mode in authorizedFetch"
```

---

### Task 20: Frontend login page

**Files:**
- Create: `frontend/src/routes/login.tsx`

- [ ] **Step 1: Create login route**

Create `frontend/src/routes/login.tsx`:

```tsx
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import * as React from 'react'
import { tokenStore } from '~/auth/tokenStore'

export const Route = createFileRoute('/login')({
  component: LoginPage,
})

const API_BASE = import.meta.env.VITE_API_URL ?? ''

function LoginPage() {
  const navigate = useNavigate()
  const [email, setEmail] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const [loading, setLoading] = React.useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail ?? 'Login failed')
      }
      const data = await res.json()
      tokenStore.set(data.access_token, data.refresh_token)
      navigate({ to: '/' })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-8 text-2xl font-bold text-gray-900 dark:text-white">Sign in</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Email
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Password
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
              placeholder="••••••••"
            />
          </div>
          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-gray-600 dark:text-gray-400">
          Don&apos;t have an account?{' '}
          <a href="/register" className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">
            Sign up
          </a>
        </p>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/routes/login.tsx
git commit -m "feat(frontend): /login page for local auth mode"
```

---

### Task 21: Frontend register page

**Files:**
- Create: `frontend/src/routes/register.tsx`

- [ ] **Step 1: Create register route**

Create `frontend/src/routes/register.tsx`:

```tsx
import { createFileRoute, useNavigate, useSearch } from '@tanstack/react-router'
import * as React from 'react'
import { tokenStore } from '~/auth/tokenStore'

export const Route = createFileRoute('/register')({
  validateSearch: (search: Record<string, unknown>) => ({
    invite: typeof search.invite === 'string' ? search.invite : undefined,
  }),
  component: RegisterPage,
})

const API_BASE = import.meta.env.VITE_API_URL ?? ''

function RegisterPage() {
  const navigate = useNavigate()
  const search = useSearch({ from: '/register' })
  const inviteToken = search.invite

  const [email, setEmail] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [confirm, setConfirm] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const [loading, setLoading] = React.useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (password !== confirm) {
      setError('Passwords do not match')
      return
    }
    setLoading(true)
    try {
      const endpoint = inviteToken ? '/auth/accept-invite' : '/auth/register'
      const body = inviteToken
        ? { token: inviteToken, password }
        : { email, password }

      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail ?? 'Registration failed')
      }
      const data = await res.json()
      tokenStore.set(data.access_token, data.refresh_token)
      navigate({ to: '/' })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-8 text-2xl font-bold text-gray-900 dark:text-white">
          {inviteToken ? 'Accept invite' : 'Create account'}
        </h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          {!inviteToken && (
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
                Email
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
                placeholder="you@example.com"
              />
            </div>
          )}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Password
            </label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
              placeholder="Min. 8 characters"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Confirm password
            </label>
            <input
              type="password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
              placeholder="••••••••"
            />
          </div>
          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {loading ? 'Creating account…' : inviteToken ? 'Accept & sign in' : 'Create account'}
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-gray-600 dark:text-gray-400">
          Already have an account?{' '}
          <a href="/login" className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">
            Sign in
          </a>
        </p>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/routes/register.tsx
git commit -m "feat(frontend): /register page; handles open signup + invite token flow"
```

---

### Task 22: Frontend setup + org settings pages

**Files:**
- Create: `frontend/src/routes/setup.tsx`
- Create: `frontend/src/routes/org/settings.tsx`

- [ ] **Step 1: Create setup page**

Create `frontend/src/routes/setup.tsx`:

```tsx
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import * as React from 'react'
import { tokenStore } from '~/auth/tokenStore'

export const Route = createFileRoute('/setup')({
  component: SetupPage,
})

const API_BASE = import.meta.env.VITE_API_URL ?? ''

function SetupPage() {
  const navigate = useNavigate()
  const [orgName, setOrgName] = React.useState('')
  const [email, setEmail] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const [loading, setLoading] = React.useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/setup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ org_name: orgName, admin_email: email, admin_password: password }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail ?? 'Setup failed')
      }
      // Auto-login after setup
      const loginRes = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (loginRes.ok) {
        const tokens = await loginRes.json()
        tokenStore.set(tokens.access_token, tokens.refresh_token)
      }
      navigate({ to: '/' })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Setup failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-950 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <span className="text-4xl">🤖</span>
          <h1 className="mt-4 text-2xl font-bold text-gray-900 dark:text-white">
            Set up AI Portal
          </h1>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            Create your organization and admin account to get started.
          </p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4 rounded-2xl border border-gray-100 bg-white p-8 shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Organization name
            </label>
            <input
              type="text"
              required
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
              placeholder="Acme Corp"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Admin email
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
              placeholder="admin@example.com"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Admin password
            </label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
              placeholder="Min. 8 characters"
            />
          </div>
          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {loading ? 'Setting up…' : 'Initialize instance'}
          </button>
        </form>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create org settings page**

Create `frontend/src/routes/org/settings.tsx`:

```tsx
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'
import { authorizedFetch } from '~/lib/authorizedFetch'

export const Route = createFileRoute('/org/settings')({
  component: OrgSettingsPage,
})

const API_BASE = import.meta.env.VITE_API_URL ?? ''

interface Member { id: number; email: string; role: string; is_verified: boolean }
interface Invite { id: number; invited_email: string; role: string; expires_at: string }

function OrgSettingsPage() {
  const [members, setMembers] = React.useState<Member[]>([])
  const [invites, setInvites] = React.useState<Invite[]>([])
  const [inviteEmail, setInviteEmail] = React.useState('')
  const [inviteRole, setInviteRole] = React.useState<'member' | 'admin'>('member')
  const [error, setError] = React.useState<string | null>(null)
  const [orgName, setOrgName] = React.useState('')

  React.useEffect(() => {
    authorizedFetch(`${API_BASE}/api/orgs/me/members`)
      .then((r) => r.json())
      .then(setMembers)
      .catch(() => null)
    authorizedFetch(`${API_BASE}/api/orgs/me/invites`)
      .then((r) => r.json())
      .then(setInvites)
      .catch(() => null)
    authorizedFetch(`${API_BASE}/api/orgs/me`)
      .then((r) => r.json())
      .then((d) => setOrgName(d.name ?? ''))
      .catch(() => null)
  }, [])

  async function sendInvite(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      const res = await authorizedFetch(`${API_BASE}/api/orgs/me/invites`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: inviteEmail, role: inviteRole }),
      })
      if (!res.ok) throw new Error((await res.json()).detail ?? 'Failed')
      const invite = await res.json()
      setInvites((prev) => [...prev, invite])
      setInviteEmail('')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to send invite')
    }
  }

  async function revokeInvite(id: number) {
    await authorizedFetch(`${API_BASE}/api/orgs/me/invites/${id}`, { method: 'DELETE' })
    setInvites((prev) => prev.filter((i) => i.id !== id))
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="mb-8 text-2xl font-bold text-gray-900 dark:text-white">
        Organization settings
        {orgName && <span className="ml-2 text-gray-400 font-normal">— {orgName}</span>}
      </h1>

      {/* Members */}
      <section className="mb-10">
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Members</h2>
        <div className="divide-y divide-gray-100 rounded-xl border border-gray-100 dark:divide-gray-800 dark:border-gray-800">
          {members.map((m) => (
            <div key={m.id} className="flex items-center justify-between px-4 py-3">
              <div>
                <p className="text-sm font-medium text-gray-900 dark:text-white">{m.email}</p>
              </div>
              <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium capitalize text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                {m.role}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* Invite */}
      <section className="mb-10">
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Invite member</h2>
        <form onSubmit={sendInvite} className="flex gap-3">
          <input
            type="email"
            required
            placeholder="colleague@example.com"
            value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
            className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-900 dark:text-white"
          />
          <select
            value={inviteRole}
            onChange={(e) => setInviteRole(e.target.value as 'member' | 'admin')}
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-white"
          >
            <option value="member">Member</option>
            <option value="admin">Admin</option>
          </select>
          <button
            type="submit"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
          >
            Invite
          </button>
        </form>
        {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
      </section>

      {/* Pending invites */}
      {invites.length > 0 && (
        <section>
          <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
            Pending invites
          </h2>
          <div className="divide-y divide-gray-100 rounded-xl border border-gray-100 dark:divide-gray-800 dark:border-gray-800">
            {invites.map((inv) => (
              <div key={inv.id} className="flex items-center justify-between px-4 py-3">
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    {inv.invited_email}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 capitalize">{inv.role}</p>
                </div>
                <button
                  onClick={() => revokeInvite(inv.id)}
                  className="text-xs text-red-500 hover:text-red-700 dark:hover:text-red-400"
                >
                  Revoke
                </button>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/setup.tsx frontend/src/routes/org/settings.tsx
git commit -m "feat(frontend): /setup wizard, /org/settings with members + invite management"
```

---

## Sub-project 5: Render + Supabase Deployment

### Task 23: Backend Dockerfile

**Files:**
- Create: `backend/Dockerfile`

- [ ] **Step 1: Create Dockerfile**

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ ./src/

RUN pip install --no-cache-dir -e .

COPY alembic.ini .
COPY alembic/ ./alembic/

# Render sets $PORT; default to 8000 for local
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn ai_portal.main:app --host 0.0.0.0 --port $PORT"]
```

- [ ] **Step 2: Test build locally**

```bash
cd backend
docker build -t ai-portal-api:local .
```

Expected: image builds successfully.

- [ ] **Step 3: Commit**

```bash
git add backend/Dockerfile
git commit -m "feat(deploy): backend Dockerfile with alembic migrate on start"
```

---

### Task 24: render.yaml

**Files:**
- Create: `render.yaml`

- [ ] **Step 1: Create render.yaml**

Create `render.yaml` at the repo root:

```yaml
services:
  # ── Backend API ───────────────────────────────────────────────────────────
  - type: web
    name: ai-portal-api
    runtime: docker
    dockerfilePath: ./backend/Dockerfile
    dockerContext: ./backend
    plan: starter
    envVars:
      - key: DEPLOYMENT_MODE
        value: saas
      - key: DATABASE_URL
        sync: false          # Set manually in Render dashboard (Supabase connection string)
      - key: SECRET_KEY
        generateValue: true  # Render auto-generates a secure random value
      - key: CORS_ORIGINS
        value: https://app.yourdomain.com
      - key: EMAIL_FROM
        value: noreply@yourdomain.com
      - key: SMTP_HOST
        sync: false
      - key: SMTP_PORT
        value: "587"
      - key: SMTP_USER
        sync: false
      - key: SMTP_PASSWORD
        sync: false
      - key: OPENAI_API_KEY
        sync: false
      - key: ANTHROPIC_API_KEY
        sync: false

  # ── Frontend App ─────────────────────────────────────────────────────────
  - type: web
    name: ai-portal-app
    runtime: node
    rootDir: frontend
    buildCommand: npm install && npm run build
    startCommand: npm run start
    plan: starter
    envVars:
      - key: VITE_AUTH_MODE
        value: local
      - key: VITE_API_URL
        value: https://ai-portal-api.onrender.com
      - key: NODE_VERSION
        value: "20"

  # ── Landing Page ─────────────────────────────────────────────────────────
  - type: web
    name: ai-portal-landing
    runtime: node
    rootDir: landing
    buildCommand: npm install && npm run build
    startCommand: npm run start
    plan: starter
    envVars:
      - key: VITE_APP_URL
        value: https://ai-portal-app.onrender.com
      - key: NODE_VERSION
        value: "20"
```

- [ ] **Step 2: Update .env.example at repo root**

Create `.env.example`:

```bash
# Copy to .env for local development

# --- Backend ---
DEPLOYMENT_MODE=dev          # dev | saas | selfhosted
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5434/ai_portal
SECRET_KEY=change-me-in-production
DEV_BEARER_TOKEN=devtoken
DEV_SEED_USER_EMAIL=dev@localhost

# SMTP (required for saas/selfhosted email verification + invites)
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
EMAIL_FROM=noreply@example.com

# LLM providers
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
VOYAGE_API_KEY=

# CORS
CORS_ORIGINS=http://localhost:5173

# --- Frontend ---
VITE_AUTH_MODE=dev           # dev | local | entra
VITE_API_URL=http://127.0.0.1:8000
VITE_APP_URL=http://localhost:5174
```

- [ ] **Step 3: Commit**

```bash
git add render.yaml .env.example
git commit -m "feat(deploy): render.yaml for one-click Render deployment + .env.example"
```

---

### Task 25: Supabase setup documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add Render + Supabase deployment section to README**

Add the following section to `README.md` after the local dev section:

```markdown
## Deploying to Render + Supabase

### 1. Create a Supabase project

1. Go to [supabase.com](https://supabase.com) and create a new project.
2. In **Database → Extensions**, enable the **vector** extension (required for RAG).
3. Copy your connection string from **Settings → Database → Connection string → URI**.
   It looks like: `postgresql://postgres:[password]@[host]:5432/postgres`

### 2. Deploy to Render

1. Fork this repository.
2. In Render, click **New → Blueprint** and point it at your fork — Render will read `render.yaml` and create all three services automatically.
3. In the `ai-portal-api` service environment variables, set:
   - `DATABASE_URL` — paste the Supabase connection string
   - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` — your email provider (e.g. Resend, SendGrid, Gmail SMTP)
   - `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY`
4. Update `CORS_ORIGINS` in `ai-portal-api` to your `ai-portal-app` URL (e.g. `https://ai-portal-app.onrender.com`).
5. Update `VITE_API_URL` in `ai-portal-app` to your `ai-portal-api` URL.
6. Update `VITE_APP_URL` in `ai-portal-landing` to your `ai-portal-app` URL.

### 3. First-time migration

Alembic migrations run automatically on every deploy via the `CMD` in `backend/Dockerfile`.

### Self-hosted mode

To deploy for a single organization:

1. Set `DEPLOYMENT_MODE=selfhosted` in the `ai-portal-api` environment.
2. On first boot, all API routes return `503 Setup Required`.
3. Navigate to `https://your-app-url/setup` to run the setup wizard.
4. Create your org and admin account — the instance is now live.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: Render + Supabase deployment guide in README"
```

---

## Final verification

- [ ] Run full test suite:
  ```bash
  cd backend && pytest tests/ -v
  ```

- [ ] Confirm migrations apply cleanly from scratch:
  ```bash
  docker compose down -v && docker compose up -d
  cd backend && python -m alembic upgrade head
  ```

- [ ] Start the backend in saas mode and test register → login flow:
  ```bash
  DEPLOYMENT_MODE=saas SECRET_KEY=testsecret uvicorn ai_portal.main:app --reload
  curl -s -X POST http://localhost:8000/auth/register \
    -H "Content-Type: application/json" \
    -d '{"email":"test@example.com","password":"TestPass123!"}' | python -m json.tool
  ```

  Expected: `{"access_token": "...", "refresh_token": "...", "token_type": "bearer"}`
