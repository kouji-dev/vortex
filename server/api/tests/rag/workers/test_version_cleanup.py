"""Version cleanup worker — unit-shaped against an in-memory fake session."""

from __future__ import annotations

import uuid as _uuid
from types import SimpleNamespace

from ai_portal.knowledge_base.model import (
    KbDocument,
    KbDocumentVersion,
    KnowledgeBase,
)
from ai_portal.rag.workers.version_cleanup import (
    DEFAULT_KEEP,
    cleanup_versions_for_document,
    cleanup_versions_for_kb,
    cleanup_versions_global,
)


class _FakeScalars:
    def __init__(self, rows):
        self._rows = list(rows)

    def __iter__(self):
        return iter(self._rows)


class _FakeDB:
    """Fake SQLAlchemy session with model-aware select/where/order_by.

    Uses introspection of the SQLAlchemy statement object directly — no SQL
    string parsing.
    """

    def __init__(self) -> None:
        self.kbs: list[KnowledgeBase] = []
        self.docs: list[KbDocument] = []
        self.versions: list[KbDocumentVersion] = []
        self.deleted: list = []
        self.commits = 0

    def _rows_for(self, model):
        if model is KnowledgeBase:
            return list(self.kbs)
        if model is KbDocument:
            return list(self.docs)
        if model is KbDocumentVersion:
            return list(self.versions)
        return []

    def _apply_filters(self, stmt, rows):
        # stmt.whereclause is either None, BinaryExpression, or BooleanClauseList.
        clause = stmt.whereclause
        if clause is None:
            return rows
        from sqlalchemy.sql.elements import BinaryExpression

        def _check(row, cl):
            if isinstance(cl, BinaryExpression):
                col_name = cl.left.key  # python attr name
                # right side is a BindParameter
                expected = cl.right.value
                return getattr(row, col_name, None) == expected
            return True

        # Walk children for AND.
        if hasattr(clause, "clauses"):
            return [r for r in rows if all(_check(r, c) for c in clause.clauses)]
        return [r for r in rows if _check(r, clause)]

    def _apply_order(self, stmt, rows):
        clauses = stmt._order_by_clauses if hasattr(stmt, "_order_by_clauses") else ()
        for clause in clauses:
            # Detect element + direction
            inner = clause.element if hasattr(clause, "element") else clause
            key = getattr(inner, "key", None)
            desc = clause.modifier is not None  # not perfect, but covers .desc()
            if key:
                rows = sorted(rows, key=lambda r: getattr(r, key), reverse=desc)
        return rows

    def scalars(self, stmt):
        model = stmt.column_descriptions[0]["entity"]
        rows = self._rows_for(model)
        rows = self._apply_filters(stmt, rows)
        rows = self._apply_order(stmt, rows)
        return _FakeScalars(rows)

    def get(self, model, obj_id):
        if model is KnowledgeBase:
            return next((k for k in self.kbs if k.id == obj_id), None)
        if model is KbDocument:
            return next((d for d in self.docs if d.id == obj_id), None)
        return None

    def delete(self, obj) -> None:
        self.deleted.append(obj)
        if isinstance(obj, KbDocumentVersion):
            self.versions = [v for v in self.versions if v is not obj]

    def commit(self) -> None:
        self.commits += 1


def _kb(*, id_: int = 1, settings: dict | None = None) -> KnowledgeBase:
    kb = KnowledgeBase(
        name=f"kb-{id_}",
        description="",
        owner_user_id=1,
        settings_json=settings or {},
    )
    kb.id = id_
    return kb


def _doc(*, kb_id: int, doc_id: _uuid.UUID | None = None) -> KbDocument:
    d = KbDocument(kb_id=kb_id, source_uri="x", title="", mime="", content_hash="")
    d.id = doc_id or _uuid.uuid4()
    return d


def _version(*, doc_id: _uuid.UUID, n: int) -> KbDocumentVersion:
    v = KbDocumentVersion(document_id=doc_id, version_no=n, content_hash=f"h{n}")
    return v


# ─── per-document ───────────────────────────────────────────────────────────


def test_cleanup_per_document_keeps_newest_n():
    db = _FakeDB()
    doc_id = _uuid.uuid4()
    db.versions = [_version(doc_id=doc_id, n=i) for i in range(1, 16)]
    deleted = cleanup_versions_for_document(db, document_id=doc_id, keep_n=10)
    assert deleted == 5
    # Remaining versions are the top 10 by version_no
    surviving = sorted(db.versions, key=lambda v: v.version_no)
    assert [v.version_no for v in surviving] == list(range(6, 16))


def test_cleanup_per_document_noop_when_under_keep():
    db = _FakeDB()
    doc_id = _uuid.uuid4()
    db.versions = [_version(doc_id=doc_id, n=i) for i in range(1, 6)]
    deleted = cleanup_versions_for_document(db, document_id=doc_id, keep_n=10)
    assert deleted == 0
    assert len(db.versions) == 5


# ─── per-kb ─────────────────────────────────────────────────────────────────


def test_cleanup_per_kb_uses_default_when_no_override():
    db = _FakeDB()
    kb = _kb(id_=42)
    db.kbs = [kb]
    d1 = _doc(kb_id=42)
    d2 = _doc(kb_id=42)
    db.docs = [d1, d2]
    db.versions = (
        [_version(doc_id=d1.id, n=i) for i in range(1, 16)]
        + [_version(doc_id=d2.id, n=i) for i in range(1, 12)]
    )
    rep = cleanup_versions_for_kb(db, kb_id=42)
    # d1: keep 10 of 15 → delete 5; d2: keep 10 of 11 → delete 1
    assert rep.versions_deleted == 6
    assert rep.kbs_processed == 1
    assert rep.documents_processed == 2
    assert db.commits == 1


def test_cleanup_per_kb_honors_settings_override():
    db = _FakeDB()
    kb = _kb(id_=7, settings={"version_retention": 3})
    db.kbs = [kb]
    d = _doc(kb_id=7)
    db.docs = [d]
    db.versions = [_version(doc_id=d.id, n=i) for i in range(1, 11)]  # 10 versions
    rep = cleanup_versions_for_kb(db, kb_id=7)
    # keep 3 → delete 7
    assert rep.versions_deleted == 7


def test_cleanup_per_kb_explicit_keep_overrides_settings():
    db = _FakeDB()
    kb = _kb(id_=7, settings={"version_retention": 3})
    db.kbs = [kb]
    d = _doc(kb_id=7)
    db.docs = [d]
    db.versions = [_version(doc_id=d.id, n=i) for i in range(1, 11)]
    rep = cleanup_versions_for_kb(db, kb_id=7, keep_n=5)
    assert rep.versions_deleted == 5  # explicit wins over settings


def test_cleanup_per_kb_no_commit_when_nothing_deleted():
    db = _FakeDB()
    kb = _kb(id_=7)
    db.kbs = [kb]
    d = _doc(kb_id=7)
    db.docs = [d]
    db.versions = [_version(doc_id=d.id, n=1)]
    rep = cleanup_versions_for_kb(db, kb_id=7)
    assert rep.versions_deleted == 0
    assert db.commits == 0


# ─── global ─────────────────────────────────────────────────────────────────


def test_cleanup_global_aggregates_counts():
    db = _FakeDB()
    kb1 = _kb(id_=1)
    kb2 = _kb(id_=2, settings={"version_retention": 2})
    db.kbs = [kb1, kb2]
    d1 = _doc(kb_id=1)
    d2 = _doc(kb_id=2)
    db.docs = [d1, d2]
    # kb1 default keep 10
    db.versions = (
        [_version(doc_id=d1.id, n=i) for i in range(1, 13)]  # 12 → del 2
        + [_version(doc_id=d2.id, n=i) for i in range(1, 6)]   # 5 → keep 2 → del 3
    )
    rep = cleanup_versions_global(db)
    assert rep.kbs_processed == 2
    assert rep.documents_processed == 2
    assert rep.versions_deleted == 5
    assert db.commits == 1


def test_cleanup_default_keep_constant_is_ten():
    assert DEFAULT_KEEP == 10
