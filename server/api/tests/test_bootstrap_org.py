"""Tests for bootstrap_org.bootstrap() core logic."""
from __future__ import annotations

import uuid

import pytest

from tests.conftest import requires_postgres

pytestmark = requires_postgres


def test_bootstrap_creates_org_and_owner(db_session):
    """bootstrap() creates a new Org and an owner User linked to it."""
    from ai_portal.scripts.bootstrap_org import bootstrap
    from ai_portal.auth.model import Org, User
    from sqlalchemy import select

    slug = f"test-{uuid.uuid4().hex[:8]}"
    email = f"owner-{uuid.uuid4().hex[:8]}@example.com"

    org, user = bootstrap(
        db_session,
        org_name="Test Org",
        org_slug=slug,
        owner_email=email,
        owner_password="hunter2",
    )

    # Org assertions
    assert org.id is not None
    assert org.slug == slug
    assert org.name == "Test Org"

    # User assertions
    assert user.id is not None
    assert user.email == email
    assert user.org_id == org.id
    assert user.role == "owner"
    assert user.is_active is True
    assert user.is_verified is True
    assert user.hashed_password is not None
    assert user.hashed_password != "hunter2"  # must be hashed

    # Verify rows visible in the same session
    db_org = db_session.scalars(select(Org).where(Org.slug == slug)).first()
    assert db_org is not None
    db_user = db_session.scalars(select(User).where(User.email == email)).first()
    assert db_user is not None


def test_bootstrap_idempotent_existing_org(db_session):
    """bootstrap() raises ValueError (not an exception that corrupts state)
    when an org with the same slug already exists."""
    from ai_portal.scripts.bootstrap_org import bootstrap

    slug = f"idem-{uuid.uuid4().hex[:8]}"
    email1 = f"owner1-{uuid.uuid4().hex[:8]}@example.com"
    email2 = f"owner2-{uuid.uuid4().hex[:8]}@example.com"

    # First call — should succeed
    org1, user1 = bootstrap(
        db_session,
        org_name="Idempotent Org",
        org_slug=slug,
        owner_email=email1,
    )
    assert org1.slug == slug

    # Second call with same slug — should raise, not create duplicate
    with pytest.raises(ValueError, match=slug):
        bootstrap(
            db_session,
            org_name="Idempotent Org Duplicate",
            org_slug=slug,
            owner_email=email2,
        )

    # Confirm only one org row with that slug exists
    from sqlalchemy import select, func
    from ai_portal.auth.model import Org

    count = db_session.scalar(
        select(func.count()).select_from(Org).where(Org.slug == slug)
    )
    assert count == 1
