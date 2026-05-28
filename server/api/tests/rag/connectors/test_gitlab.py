"""gitlab connector — docs + issues with a fake API client."""

from __future__ import annotations

import pytest


class _FakeGitlabClient:
    async def list_projects(self, scope_type, scope_id):
        return [{"id": 42, "path_with_namespace": scope_id}]

    async def list_docs(self, project_id):
        return [{"path": "README.md"}, {"path": "docs/intro.md"}]

    async def list_issues(self, project_id):
        return [
            {
                "iid": 1,
                "title": "first",
                "description": "body1",
                "updated_at": "2026-05-01T00:00:00Z",
            },
            {
                "iid": 2,
                "title": "second",
                "description": "body2",
                "updated_at": "2026-05-10T00:00:00Z",
            },
        ]

    async def get_blob(self, project_id, path):
        return f"bytes:{project_id}:{path}".encode()

    async def list_members(self, project_id):
        return ["alice", "carol"]


class _SecretStore:
    def __init__(self, client):
        self.gitlab_client = client


@pytest.mark.asyncio
async def test_gitlab_discover_fetch_and_acls():
    from ai_portal.rag.connectors.adapters.gitlab import GitlabConnector

    conn = await GitlabConnector.setup(
        config={"scope_type": "project", "scope_id": "g/p"},
        secret_store=_SecretStore(_FakeGitlabClient()),
    )
    docs = [sd async for sd in conn.discover(cursor=None)]
    uris = {d.source_uri for d in docs}
    assert "gitlab://g/p/blob/README.md" in uris
    assert "gitlab://g/p/blob/docs/intro.md" in uris
    assert "gitlab://g/p/issues/1" in uris
    assert "gitlab://g/p/issues/2" in uris

    readme = next(d for d in docs if d.source_uri.endswith("README.md"))
    f = await conn.fetch(readme)
    assert f.data == b"bytes:42:README.md"

    acl = await conn.acls(readme)
    assert acl.user_ids == {"alice", "carol"}


@pytest.mark.asyncio
async def test_gitlab_delta_skips_old_issues():
    from ai_portal.rag.connectors.adapters.gitlab import GitlabConnector

    conn = await GitlabConnector.setup(
        config={"scope_type": "project", "scope_id": "g/p"},
        secret_store=_SecretStore(_FakeGitlabClient()),
    )
    docs = [
        sd async for sd in conn.discover(cursor="2026-05-05T00:00:00Z")
    ]
    assert any(d.source_uri.endswith("issues/2") for d in docs)
    assert not any(d.source_uri.endswith("issues/1") for d in docs)
