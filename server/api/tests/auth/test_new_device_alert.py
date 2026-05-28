"""Login alert — new-device detection + hook dispatch.

File-scoped: stubs the SQLAlchemy session with a minimal in-memory fake so the
test runs without Postgres. Asserts:
- is_new_device() returns True when no prior session matches (ip, UA)
- is_new_device() returns False when a prior session matches
- create_session() fires the new-device hook exactly once on a new device
- create_session() does NOT fire the hook when device is recognized
- The hook payload contains user_id, ip, user_agent, ts
- set_new_device_hook(None) restores the default no-op behaviour
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ai_portal.auth import sessions as sess
from ai_portal.auth.model import UserSession


# ── Fake SQLAlchemy session ─────────────────────────────────────────────────


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDb:
    def __init__(self, sessions: list[UserSession] | None = None) -> None:
        self.sessions = sessions or []
        self.added: list = []
        self.committed = 0

    def scalars(self, _stmt):
        # Always return all stored sessions; the production filter is on
        # user_id + created_at >= since, but for these unit tests we control
        # the corpus and check the in-Python comparison logic.
        return _Scalars(self.sessions)

    def add(self, obj) -> None:
        self.added.append(obj)
        self.sessions.append(obj)

    def commit(self) -> None:
        self.committed += 1

    def refresh(self, _obj) -> None:
        pass


def _mk(user_id, ip, ua, days_ago=0) -> UserSession:
    s = UserSession()
    s.user_id = user_id
    s.ip = ip
    s.user_agent = ua
    s.created_at = datetime.now(UTC) - timedelta(days=days_ago)
    s.expires_at = datetime.now(UTC) + timedelta(days=30)
    return s


# ── is_new_device ───────────────────────────────────────────────────────────


def test_is_new_device_true_when_no_history():
    db = _FakeDb([])
    assert sess.is_new_device(db, user_id=1, ip="1.1.1.1", user_agent="UA") is True


def test_is_new_device_false_when_matching_session_exists():
    db = _FakeDb([_mk(1, "1.1.1.1", "Mozilla/5.0 X")])
    assert (
        sess.is_new_device(db, user_id=1, ip="1.1.1.1", user_agent="Mozilla/5.0 X")
        is False
    )


def test_is_new_device_true_on_different_ip():
    db = _FakeDb([_mk(1, "1.1.1.1", "UA")])
    assert sess.is_new_device(db, user_id=1, ip="2.2.2.2", user_agent="UA") is True


def test_is_new_device_true_on_different_ua():
    db = _FakeDb([_mk(1, "1.1.1.1", "Chrome")])
    assert (
        sess.is_new_device(db, user_id=1, ip="1.1.1.1", user_agent="Safari") is True
    )


def test_is_new_device_handles_none_ua():
    db = _FakeDb([_mk(1, "1.1.1.1", None)])
    assert sess.is_new_device(db, user_id=1, ip="1.1.1.1", user_agent=None) is False


# ── create_session hook dispatch ────────────────────────────────────────────


@pytest.fixture
def captured_hook(monkeypatch):
    calls = []

    def hook(user_id, ip, ua, ts):
        calls.append({"user_id": user_id, "ip": ip, "ua": ua, "ts": ts})

    sess.set_new_device_hook(hook)
    yield calls
    sess.set_new_device_hook(None)  # restore default


def test_create_session_fires_hook_on_new_device(captured_hook):
    db = _FakeDb([])
    sess.create_session(
        db,
        user_id=42,
        refresh_token="rt-new",
        ip="9.9.9.9",
        user_agent="NewUA",
    )
    assert len(captured_hook) == 1
    evt = captured_hook[0]
    assert evt["user_id"] == 42
    assert evt["ip"] == "9.9.9.9"
    assert evt["ua"] == "NewUA"
    assert isinstance(evt["ts"], datetime)


def test_create_session_skips_hook_on_known_device(captured_hook):
    db = _FakeDb([_mk(42, "9.9.9.9", "KnownUA")])
    sess.create_session(
        db,
        user_id=42,
        refresh_token="rt-2",
        ip="9.9.9.9",
        user_agent="KnownUA",
    )
    assert captured_hook == []


def test_hook_exception_does_not_break_session_creation(monkeypatch):
    def boom(*_a, **_kw):
        raise RuntimeError("notify down")

    sess.set_new_device_hook(boom)
    try:
        db = _FakeDb([])
        # Must not raise.
        sess.create_session(
            db,
            user_id=1,
            refresh_token="rt",
            ip="1.1.1.1",
            user_agent="X",
        )
        assert db.committed >= 1
    finally:
        sess.set_new_device_hook(None)


def test_set_new_device_hook_none_restores_default(captured_hook):
    sess.set_new_device_hook(None)
    db = _FakeDb([])
    sess.create_session(
        db, user_id=1, refresh_token="rt", ip="1.1.1.1", user_agent="X"
    )
    # Default hook (logger) does not append to our capture list.
    assert captured_hook == []
