"""Tests for OrgService — create / update / invite / membership."""
from __future__ import annotations

import secrets

import pytest

from ai_portal.auth.model import User
from ai_portal.auth.orgs_schemas import OrgCreate, OrgUpdate
from ai_portal.auth.orgs_service import (
    InviteExpired,
    InviteNotFound,
    NotAMember,
    OrgNotFound,
    OrgService,
    OrgSlugTaken,
)
from ai_portal.core.db.session import SessionLocal
from tests.conftest import requires_postgres


def _rand_slug() -> str:
    return "t-" + secrets.token_hex(4)


def _make_user(db, email: str) -> User:
    import uuid as _uuid
    user = User(
        email=email.lower().strip(),
        uuid=_uuid.uuid4(),
        is_active=True,
        is_verified=False,
        role="member",
    )
    db.add(user)
    db.flush()
    return user


# ── Create / update ──────────────────────────────────────────────────────────


@requires_postgres
def test_create_org_returns_org():
    db = SessionLocal()
    try:
        svc = OrgService(db)
        org = svc.create(OrgCreate(slug=_rand_slug(), name="Acme"))
        assert org.id is not None
        assert org.region == "eu-west-1"
        assert org.status == "active"
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_create_org_duplicate_slug_raises():
    db = SessionLocal()
    try:
        slug = _rand_slug()
        svc = OrgService(db)
        svc.create(OrgCreate(slug=slug, name="Acme"))
        with pytest.raises(OrgSlugTaken):
            svc.create(OrgCreate(slug=slug, name="Other"))
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_update_org_renames():
    db = SessionLocal()
    try:
        svc = OrgService(db)
        org = svc.create(OrgCreate(slug=_rand_slug(), name="Old"))
        updated = svc.update(org.id, OrgUpdate(name="New"))
        assert updated.name == "New"
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_update_org_slug_collision_raises():
    db = SessionLocal()
    try:
        svc = OrgService(db)
        a = svc.create(OrgCreate(slug=_rand_slug(), name="A"))
        b = svc.create(OrgCreate(slug=_rand_slug(), name="B"))
        with pytest.raises(OrgSlugTaken):
            svc.update(b.id, OrgUpdate(slug=a.slug))
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_get_missing_org_raises():
    import uuid as _uuid

    db = SessionLocal()
    try:
        svc = OrgService(db)
        with pytest.raises(OrgNotFound):
            svc.get(_uuid.uuid4())
    finally:
        db.rollback()
        db.close()


# ── Invitations ──────────────────────────────────────────────────────────────


@requires_postgres
def test_invite_then_accept_assigns_membership():
    db = SessionLocal()
    try:
        svc = OrgService(db)
        org = svc.create(OrgCreate(slug=_rand_slug(), name="Acme"))
        invitee_email = f"x-{secrets.token_hex(4)}@acme.test"
        user = _make_user(db, invitee_email)

        inv = svc.invite(org.id, email=invitee_email, role="admin", by=user.id)
        assert inv.token
        assert inv.role == "admin"

        member = svc.accept_invitation(inv.token, user)
        assert member.org_id == org.id
        assert member.role == "admin"
        assert svc.is_member(org.id, user.id) is True
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_accept_invite_with_wrong_email_rejected():
    db = SessionLocal()
    try:
        svc = OrgService(db)
        org = svc.create(OrgCreate(slug=_rand_slug(), name="Acme"))
        inv = svc.invite(org.id, email="invited@acme.test", role="member")

        other = _make_user(db, f"other-{secrets.token_hex(4)}@acme.test")
        with pytest.raises(InviteNotFound):
            svc.accept_invitation(inv.token, other)
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_expired_invite_raises():
    from datetime import UTC, datetime, timedelta

    db = SessionLocal()
    try:
        svc = OrgService(db)
        org = svc.create(OrgCreate(slug=_rand_slug(), name="Acme"))
        email = f"exp-{secrets.token_hex(4)}@acme.test"
        inv = svc.invite(org.id, email=email)
        inv.expires_at = datetime.now(UTC) - timedelta(days=1)
        db.commit()
        with pytest.raises(InviteExpired):
            svc.get_invite_by_token(inv.token)
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_second_invite_revokes_first():
    db = SessionLocal()
    try:
        svc = OrgService(db)
        org = svc.create(OrgCreate(slug=_rand_slug(), name="Acme"))
        email = f"dupe-{secrets.token_hex(4)}@acme.test"
        first = svc.invite(org.id, email=email)
        second = svc.invite(org.id, email=email)
        # Re-fetch first; it should be revoked.
        db.refresh(first)
        assert first.revoked_at is not None
        assert second.id != first.id
    finally:
        db.rollback()
        db.close()


# ── Membership ───────────────────────────────────────────────────────────────


@requires_postgres
def test_remove_member_marks_removed():
    db = SessionLocal()
    try:
        svc = OrgService(db)
        org = svc.create(OrgCreate(slug=_rand_slug(), name="Acme"))
        user = _make_user(db, f"m-{secrets.token_hex(4)}@acme.test")
        svc.add_member(org.id, user.id, role="member")
        assert svc.is_member(org.id, user.id) is True
        svc.remove_member(org.id, user.id)
        assert svc.is_member(org.id, user.id) is False
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_remove_unknown_member_raises():
    db = SessionLocal()
    try:
        svc = OrgService(db)
        org = svc.create(OrgCreate(slug=_rand_slug(), name="Acme"))
        with pytest.raises(NotAMember):
            svc.remove_member(org.id, 999_999_999)
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_add_member_idempotent_updates_role():
    db = SessionLocal()
    try:
        svc = OrgService(db)
        org = svc.create(OrgCreate(slug=_rand_slug(), name="Acme"))
        user = _make_user(db, f"i-{secrets.token_hex(4)}@acme.test")
        first = svc.add_member(org.id, user.id, role="member")
        second = svc.add_member(org.id, user.id, role="admin")
        assert first.id == second.id
        assert second.role == "admin"
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_list_members_excludes_removed():
    db = SessionLocal()
    try:
        svc = OrgService(db)
        org = svc.create(OrgCreate(slug=_rand_slug(), name="Acme"))
        u1 = _make_user(db, f"l1-{secrets.token_hex(4)}@acme.test")
        u2 = _make_user(db, f"l2-{secrets.token_hex(4)}@acme.test")
        svc.add_member(org.id, u1.id)
        svc.add_member(org.id, u2.id)
        db.commit()
        svc.remove_member(org.id, u2.id)
        members = svc.list_members(org.id)
        assert {m.user_id for m in members} == {u1.id}
    finally:
        db.rollback()
        db.close()
