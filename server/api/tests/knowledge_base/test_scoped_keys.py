"""Phase A: per-KB scoped API key helpers."""

from __future__ import annotations

from types import SimpleNamespace

from ai_portal.knowledge_base.scoped_keys import (
    SCOPE_KB_ANSWER,
    SCOPE_KB_READ,
    kb_id_for_key,
    key_permits,
)


def _fake_key(scopes: list[str]):
    return SimpleNamespace(scopes_json=scopes)


def test_kb_id_for_key_extracts_resource_token():
    key = _fake_key([SCOPE_KB_READ, "kb:42"])
    assert kb_id_for_key(key) == 42


def test_kb_id_for_key_none_when_unbound():
    key = _fake_key([SCOPE_KB_READ])
    assert kb_id_for_key(key) is None


def test_kb_id_for_key_ignores_bad_token():
    key = _fake_key([SCOPE_KB_READ, "kb:notanint"])
    assert kb_id_for_key(key) is None


def test_key_permits_requires_scope_and_kb_binding():
    key = _fake_key([SCOPE_KB_READ, SCOPE_KB_ANSWER, "kb:7"])
    assert key_permits(key, SCOPE_KB_READ, kb_id=7)
    assert key_permits(key, SCOPE_KB_ANSWER, kb_id=7)
    # wrong kb
    assert not key_permits(key, SCOPE_KB_READ, kb_id=8)
    # scope absent
    assert not key_permits(key, "kb:write", kb_id=7)


def test_key_permits_rejects_empty_scopes():
    key = _fake_key([])
    assert not key_permits(key, SCOPE_KB_READ, kb_id=1)


# ── list / get scoped keys (DB-shaped fake) ─────────────────────────────────


import uuid as _uuid

from ai_portal.knowledge_base.scoped_keys import (
    get_scoped_kb_key,
    list_scoped_kb_keys,
)


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows
        self.calls = []

    def scalars(self, stmt):
        self.calls.append(stmt)
        return _FakeScalars(self._rows)


def _row(id_=None, scopes=None, org_id="org-a", revoked=None):
    from datetime import UTC, datetime

    return SimpleNamespace(
        id=id_ or _uuid.uuid4(),
        org_id=org_id,
        scopes_json=scopes or [],
        revoked_at=revoked,
        name="n",
        prefix="ap_xxx",
        created_at=datetime.now(UTC),
        last_used_at=None,
    )


def test_list_scoped_kb_keys_filters_by_kb_token():
    org = "org-a"
    rows = [
        _row(scopes=[SCOPE_KB_READ, "kb:5"], org_id=org),
        _row(scopes=[SCOPE_KB_READ, "kb:6"], org_id=org),
        _row(scopes=[SCOPE_KB_READ], org_id=org),
    ]
    db = _FakeDB(rows)
    out = list_scoped_kb_keys(db, org_id=org, kb_id=5)
    assert len(out) == 1
    assert "kb:5" in out[0].scopes_json


def test_list_scoped_kb_keys_excludes_revoked_by_default():
    from datetime import UTC, datetime
    org = "org-a"
    rows = [
        _row(scopes=[SCOPE_KB_READ, "kb:5"], org_id=org),
        _row(scopes=[SCOPE_KB_READ, "kb:5"], org_id=org, revoked=datetime.now(UTC)),
    ]
    db = _FakeDB(rows)
    out_active = list_scoped_kb_keys(db, org_id=org, kb_id=5)
    out_all = list_scoped_kb_keys(db, org_id=org, kb_id=5, include_revoked=True)
    assert len(out_active) == 1
    assert len(out_all) == 2


def test_get_scoped_kb_key_returns_none_when_not_bound():
    org = "org-a"
    row = _row(scopes=[SCOPE_KB_READ, "kb:5"], org_id=org)
    db = _FakeDB([row])
    # Asking for the wrong KB → None.
    assert get_scoped_kb_key(db, org_id=org, kb_id=9, key_id=row.id) is None
    # Right KB → the row.
    got = get_scoped_kb_key(db, org_id=org, kb_id=5, key_id=row.id)
    assert got is row


def test_get_scoped_kb_key_returns_none_when_missing():
    db = _FakeDB([])
    assert get_scoped_kb_key(db, org_id="org-a", kb_id=1, key_id=_uuid.uuid4()) is None
