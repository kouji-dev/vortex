"""OrgService.restore() — 30-day soft-delete recovery window.

File-scoped: stubs OrgRepo + Session so the service can run without Postgres.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime, timedelta

import pytest

from ai_portal.auth.model import Org
from ai_portal.auth.orgs_service import (
    ORG_RESTORE_WINDOW_DAYS,
    OrgNotArchived,
    OrgNotFound,
    OrgRestoreWindowExpired,
    OrgService,
)


class _FakeRepo:
    def __init__(self, org: Org | None) -> None:
        self.org = org

    def by_id(self, _org_id):
        return self.org

    def by_slug(self, _slug):
        return None

    def add(self, _obj):
        pass


class _FakeDb:
    def __init__(self) -> None:
        self.committed = 0

    def commit(self):
        self.committed += 1

    def refresh(self, _obj):
        pass

    def scalars(self, _stmt):
        class _S:
            def first(self_inner):
                return None

            def all(self_inner):
                return []

        return _S()

    def get(self, _cls, _id):
        return None

    def flush(self):
        pass

    def add(self, _obj):
        pass


def _mk_org(*, archived_days_ago: int | None) -> Org:
    org = Org()
    org.id = _uuid.uuid4()
    org.slug = "acme"
    org.name = "Acme"
    org.region = "eu-west-1"
    org.status = "active"
    org.instance_mode = False
    if archived_days_ago is None:
        org.archived_at = None
    else:
        org.archived_at = datetime.now(UTC) - timedelta(days=archived_days_ago)
    return org


def _svc(org: Org | None) -> OrgService:
    svc = OrgService.__new__(OrgService)
    svc.db = _FakeDb()
    svc.repo = _FakeRepo(org)
    return svc


# ── happy path ───────────────────────────────────────────────────────────────


def test_restore_within_window_clears_archived_at():
    org = _mk_org(archived_days_ago=5)
    svc = _svc(org)
    restored = svc.restore(org.id)
    assert restored.archived_at is None


def test_restore_at_boundary_succeeds():
    # Just under the limit — must succeed.
    org = _mk_org(archived_days_ago=ORG_RESTORE_WINDOW_DAYS - 1)
    svc = _svc(org)
    restored = svc.restore(org.id)
    assert restored.archived_at is None


# ── errors ───────────────────────────────────────────────────────────────────


def test_restore_unknown_org_raises_not_found():
    svc = _svc(None)
    with pytest.raises(OrgNotFound):
        svc.restore(_uuid.uuid4())


def test_restore_not_archived_raises():
    org = _mk_org(archived_days_ago=None)
    svc = _svc(org)
    with pytest.raises(OrgNotArchived):
        svc.restore(org.id)


def test_restore_after_30_days_raises_window_expired():
    org = _mk_org(archived_days_ago=ORG_RESTORE_WINDOW_DAYS + 1)
    svc = _svc(org)
    with pytest.raises(OrgRestoreWindowExpired):
        svc.restore(org.id)


def test_restore_far_past_raises_window_expired():
    org = _mk_org(archived_days_ago=365)
    svc = _svc(org)
    with pytest.raises(OrgRestoreWindowExpired):
        svc.restore(org.id)


# ── archive helper ───────────────────────────────────────────────────────────


def test_archive_stamps_archived_at():
    org = _mk_org(archived_days_ago=None)
    svc = _svc(org)
    archived = svc.archive(org.id)
    assert archived.archived_at is not None


def test_archive_idempotent_does_not_overwrite_existing_archive():
    org = _mk_org(archived_days_ago=5)
    original = org.archived_at
    svc = _svc(org)
    again = svc.archive(org.id)
    assert again.archived_at == original
