"""OIDC group claims → RAG ACL group resolution.

Covers:
- jit_provision stores groups from OIDC claims in user.idp_groups
- jit_provision updates idp_groups on re-login
- IdpMapper.resolve_group returns identity (group name unchanged)
- _load_user_group_ids returns stored idp_groups
- user NOT in a group does not resolve membership
"""
from __future__ import annotations

import uuid
import pytest
from sqlalchemy import select

from ai_portal.auth.idp.protocol import UserClaims
from ai_portal.auth.model import User
from ai_portal.auth.oidc.provisioning import jit_provision
from ai_portal.rag.acl.idp_mapping import IdpMapper
from ai_portal.rag.acl.permission_test import _load_user_group_ids
from tests.conftest import requires_postgres

pytestmark = requires_postgres


def test_jit_provision_stores_groups(db_session, org):
    """jit_provision on new user stores groups from OIDC claims."""
    claims = UserClaims(
        subject="oidc|eng1",
        email=f"eng-{uuid.uuid4().hex[:6]}@acme.test",
        name="Engineer One",
        groups=("Engineering", "Platform"),
    )
    user = jit_provision(db_session, claims=claims, org_id=org.id, role="member")
    db_session.flush()
    assert user.idp_groups == ["Engineering", "Platform"]


def test_jit_provision_updates_groups_on_relogin(db_session, org):
    """jit_provision updates idp_groups when user logs in again with new groups."""
    email = f"eng-{uuid.uuid4().hex[:6]}@acme.test"
    claims_v1 = UserClaims(
        subject="oidc|eng2",
        email=email,
        name="Engineer Two",
        groups=("Engineering",),
    )
    user = jit_provision(db_session, claims=claims_v1, org_id=org.id, role="member")
    db_session.flush()
    assert user.idp_groups == ["Engineering"]

    claims_v2 = UserClaims(
        subject="oidc|eng2",
        email=email,
        name="Engineer Two",
        groups=("Engineering", "Leads"),
    )
    user2 = jit_provision(db_session, claims=claims_v2, org_id=org.id, role="member")
    db_session.flush()
    assert user.id == user2.id
    assert user2.idp_groups == ["Engineering", "Leads"]


def test_jit_provision_empty_groups(db_session, org):
    """jit_provision with no groups stores empty list."""
    claims = UserClaims(
        subject="oidc|eng3",
        email=f"nogrp-{uuid.uuid4().hex[:6]}@acme.test",
        name="No Groups",
        groups=(),
    )
    user = jit_provision(db_session, claims=claims, org_id=org.id, role="member")
    db_session.flush()
    assert user.idp_groups == []


def test_idp_mapper_resolve_group_identity(db_session, org):
    """IdpMapper.resolve_group returns the group name unchanged (identity match)."""
    mapper = IdpMapper(db=db_session, org_id=org.id)
    assert mapper.resolve_group("Engineering") == "Engineering"
    assert mapper.resolve_group("platform-leads") == "platform-leads"
    assert mapper.resolve_group("") == ""


def test_idp_mapper_resolve_group_not_none(db_session, org):
    """resolve_group is not None — OIDC groups always resolve via identity."""
    mapper = IdpMapper(db=db_session, org_id=org.id)
    result = mapper.resolve_group("Engineering")
    assert result is not None


def test_load_user_group_ids_returns_idp_groups(db_session, org):
    """_load_user_group_ids returns the user's idp_groups list."""
    claims = UserClaims(
        subject="oidc|eng4",
        email=f"grpload-{uuid.uuid4().hex[:6]}@acme.test",
        name="Group Load",
        groups=("Engineering", "Backend"),
    )
    user = jit_provision(db_session, claims=claims, org_id=org.id, role="member")
    db_session.flush()

    group_ids = _load_user_group_ids(db_session, user.id)
    assert group_ids == ["Engineering", "Backend"]


def test_user_not_in_group_does_not_resolve(db_session, org):
    """A user without a group in idp_groups is not a member of that group."""
    claims = UserClaims(
        subject="oidc|eng5",
        email=f"noeng-{uuid.uuid4().hex[:6]}@acme.test",
        name="Not Engineering",
        groups=("Marketing",),
    )
    user = jit_provision(db_session, claims=claims, org_id=org.id, role="member")
    db_session.flush()

    group_ids = _load_user_group_ids(db_session, user.id)
    assert "Engineering" not in group_ids
    assert "Marketing" in group_ids
