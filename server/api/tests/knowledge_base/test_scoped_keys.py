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
