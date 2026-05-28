"""Sync orchestrator tests.

The orchestrator drives ``Connector.discover``, persists per-document state
via a job-emitter callback, captures errors per source-doc, and updates the
delta cursor on success.

These tests use an in-memory ``_FakeRepo`` so they stay file-scoped.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from ai_portal.rag.connectors import (
    AclSet,
    ConnectorManifest,
    FetchedDoc,
    SourceDoc,
)


class _FakeConnector:
    manifest = ConnectorManifest(
        name="fake_orchestrator",
        auth_kinds=("none",),
        schedulable=True,
        supports_delta=True,
        supports_acl=False,
        supports_webhook=False,
    )

    def __init__(
        self,
        docs: list[SourceDoc],
        raises_on: set[str] | None = None,
        cursor_after: str | None = None,
    ):
        self._docs = docs
        self._raises = raises_on or set()
        self._cursor: str | None = None
        self._cursor_after = cursor_after

    @classmethod
    async def setup(cls, config, secret_store):  # pragma: no cover - unused
        return cls([])

    async def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        for sd in self._docs:
            if sd.source_uri in self._raises:
                raise RuntimeError(f"discover failure on {sd.source_uri}")
            yield sd

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:  # pragma: no cover
        return FetchedDoc(data=b"", mime="text/plain")

    async def acls(self, sd: SourceDoc) -> AclSet:  # pragma: no cover
        return AclSet()

    async def delta_cursor(self) -> str | None:
        return self._cursor_after or self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


class _FakeRepo:
    def __init__(self):
        self.runs = []
        self.errors = []
        self.cursor = None
        self.last_sync_at = None

    async def start_run(self, connector_id):
        self.runs.append(
            {
                "connector_id": connector_id,
                "started_at": datetime.now(UTC),
                "status": "running",
                "docs_added": 0,
                "docs_updated": 0,
                "errors_count": 0,
                "ended_at": None,
                "cursor_after": None,
            }
        )
        return len(self.runs) - 1

    async def end_run(self, run_id, *, status, cursor_after):
        self.runs[run_id]["status"] = status
        self.runs[run_id]["ended_at"] = datetime.now(UTC)
        self.runs[run_id]["cursor_after"] = cursor_after

    async def increment(self, run_id, *, added=0, updated=0, errors=0):
        self.runs[run_id]["docs_added"] += added
        self.runs[run_id]["docs_updated"] += updated
        self.runs[run_id]["errors_count"] += errors

    async def record_error(self, run_id, source_uri, error):
        self.errors.append(
            {"run_id": run_id, "source_uri": source_uri, "error": error}
        )

    async def update_connector_cursor(self, connector_id, cursor, last_sync_at):
        self.cursor = cursor
        self.last_sync_at = last_sync_at


def _sd(uri: str, lastmod: str | None = None) -> SourceDoc:
    return SourceDoc(
        source_uri=uri,
        title=uri,
        mime="text/plain",
        size=None,
        modified_at=None,
        cursor_token=lastmod,
    )


# ----------------------------------------------------------- tests --

@pytest.mark.asyncio
async def test_orchestrator_enqueues_one_job_per_doc_and_finishes_success():
    from ai_portal.rag.connectors.sync_service import SyncOrchestrator

    enqueued: list[str] = []
    connector = _FakeConnector(
        docs=[_sd("a", "2026-05-01"), _sd("b", "2026-05-02")],
        cursor_after="2026-05-02",
    )
    repo = _FakeRepo()
    orch = SyncOrchestrator(
        repo=repo,
        enqueue_ingest=lambda doc: enqueued.append(doc.source_uri),
    )
    result = await orch.run(connector_id="cid-1", connector=connector)
    assert enqueued == ["a", "b"]
    assert repo.runs[0]["status"] == "success"
    assert repo.runs[0]["docs_added"] == 2
    assert repo.runs[0]["errors_count"] == 0
    assert repo.cursor == "2026-05-02"
    assert result.errors == []


@pytest.mark.asyncio
async def test_orchestrator_isolates_per_doc_errors_partial_status():
    from ai_portal.rag.connectors.sync_service import SyncOrchestrator

    enqueued: list[str] = []
    repo = _FakeRepo()

    def enqueue(doc: SourceDoc):
        if doc.source_uri == "b":
            raise RuntimeError("enqueue failed for b")
        enqueued.append(doc.source_uri)

    connector = _FakeConnector(
        docs=[_sd("a"), _sd("b"), _sd("c")],
        cursor_after="2026-05-03",
    )
    orch = SyncOrchestrator(repo=repo, enqueue_ingest=enqueue)
    result = await orch.run(connector_id="cid-2", connector=connector)
    assert enqueued == ["a", "c"]
    assert repo.runs[0]["status"] == "partial"
    assert repo.runs[0]["errors_count"] == 1
    assert repo.errors[0]["source_uri"] == "b"
    assert repo.errors[0]["error"].startswith("enqueue failed")
    assert result.errors == [("b", "enqueue failed for b")]


@pytest.mark.asyncio
async def test_orchestrator_marks_failed_when_discover_explodes():
    from ai_portal.rag.connectors.sync_service import SyncOrchestrator

    repo = _FakeRepo()
    connector = _FakeConnector(
        docs=[_sd("a"), _sd("BOOM"), _sd("c")],
        raises_on={"BOOM"},
    )
    orch = SyncOrchestrator(repo=repo, enqueue_ingest=lambda _d: None)
    result = await orch.run(connector_id="cid-3", connector=connector)
    assert repo.runs[0]["status"] == "failed"
    assert result.discover_error is not None
