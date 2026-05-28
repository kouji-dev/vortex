"""Phase A: KB management visibility filter unit tests."""

from __future__ import annotations

from types import SimpleNamespace

from ai_portal.knowledge_base.management import VisibilityFilter
from ai_portal.knowledge_base.model import KbVisibility


def _kb(*, visibility: str, owner: int, org: str, settings: dict | None = None):
    return SimpleNamespace(
        visibility=visibility,
        owner_user_id=owner,
        org_id=org,
        settings_json=settings or {},
    )


def test_private_kb_visible_only_to_owner():
    f = VisibilityFilter(user_id=1, org_id="org-a")
    own = _kb(visibility=KbVisibility.private.value, owner=1, org="org-a")
    foreign = _kb(visibility=KbVisibility.private.value, owner=2, org="org-a")
    assert f.applies_to(own)
    assert not f.applies_to(foreign)


def test_org_public_kb_visible_to_anyone_in_same_org():
    f = VisibilityFilter(user_id=99, org_id="org-a")
    kb = _kb(visibility=KbVisibility.org_public.value, owner=1, org="org-a")
    assert f.applies_to(kb)
    other_org = _kb(visibility=KbVisibility.org_public.value, owner=1, org="org-b")
    assert not f.applies_to(other_org)


def test_team_kb_filtered_by_team_membership():
    kb = _kb(
        visibility=KbVisibility.team.value,
        owner=1,
        org="org-a",
        settings={"team_id": "t-7"},
    )
    member = VisibilityFilter(user_id=2, org_id="org-a", team_ids=("t-7",))
    stranger = VisibilityFilter(user_id=3, org_id="org-a", team_ids=("t-8",))
    assert member.applies_to(kb)
    assert not stranger.applies_to(kb)


def test_team_kb_without_team_id_setting_visible_to_all_team_members():
    """Best-effort: when settings doesn't carry team_id, treat as team-wide."""
    kb = _kb(visibility=KbVisibility.team.value, owner=1, org="org-a", settings={})
    f = VisibilityFilter(user_id=2, org_id="org-a", team_ids=())
    assert f.applies_to(kb)


def test_unknown_visibility_hidden():
    kb = _kb(visibility="weird", owner=1, org="org-a")
    f = VisibilityFilter(user_id=1, org_id="org-a")
    assert not f.applies_to(kb)


# ── copy_documents -----------------------------------------------------------


from ai_portal.knowledge_base.management import copy_documents
from ai_portal.knowledge_base.model import Document


class _CapturingDB:
    """Minimal SQLAlchemy session double for copy_documents tests."""

    def __init__(self, src_docs):
        self._src_docs = list(src_docs)
        self.added: list = []
        self.commits = 0

    def scalars(self, stmt):
        return iter(self._src_docs)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1


def test_copy_documents_copies_metadata_only():
    src = [
        Document(knowledge_base_id=1, filename="a.pdf", storage_path="/s/a"),
        Document(knowledge_base_id=1, filename="b.pdf", storage_path="/s/b"),
    ]
    db = _CapturingDB(src)
    n = copy_documents(db, src_kb_id=1, dst_kb_id=2)
    assert n == 2
    assert len(db.added) == 2
    for d in db.added:
        assert d.knowledge_base_id == 2
        assert d.status == "pending"  # re-ingest, not "ready"
    assert db.commits == 1


def test_copy_documents_no_commit_when_empty():
    db = _CapturingDB([])
    n = copy_documents(db, src_kb_id=1, dst_kb_id=2)
    assert n == 0
    assert db.added == []
    assert db.commits == 0


def test_copy_documents_default_status_is_pending_not_ready():
    """Cloned documents must re-ingest. Carrying over 'indexed' would expose stale chunks."""
    src = [
        Document(
            knowledge_base_id=1,
            filename="a.pdf",
            storage_path="/s/a",
            status="indexed",
        )
    ]
    db = _CapturingDB(src)
    copy_documents(db, src_kb_id=1, dst_kb_id=2)
    assert db.added[0].status == "pending"
