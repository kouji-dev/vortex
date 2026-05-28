"""github connector — docs + issues with a fake API client."""

from __future__ import annotations

import pytest


class _FakeGithubClient:
    async def list_repos(self, scope_type, scope_id):
        if scope_type == "org":
            return [{"full_name": f"{scope_id}/repo1", "name": "repo1"}]
        return [{"full_name": scope_id, "name": scope_id.split("/")[-1]}]

    async def list_docs(self, repo_full_name):
        return [
            {"path": "README.md", "sha": "sha-readme"},
            {"path": "docs/intro.md", "sha": "sha-intro"},
        ]

    async def list_issues(self, repo_full_name):
        return [
            {
                "number": 1,
                "title": "bug",
                "body": "found a bug",
                "updated_at": "2026-05-01T00:00:00Z",
                "is_pull": False,
            },
            {
                "number": 2,
                "title": "fix",
                "body": "fix description",
                "updated_at": "2026-05-10T00:00:00Z",
                "is_pull": True,
            },
        ]

    async def get_blob(self, repo_full_name, path):
        return f"bytes:{repo_full_name}:{path}".encode()

    async def list_collaborators(self, repo_full_name):
        return ["alice", "bob"]


class _SecretStore:
    def __init__(self, client):
        self.github_client = client


@pytest.mark.asyncio
async def test_github_discover_docs_issues_pulls_and_acls():
    from ai_portal.rag.connectors.adapters.github import GithubConnector

    conn = await GithubConnector.setup(
        config={"scope_type": "repo", "scope_id": "x/y"},
        secret_store=_SecretStore(_FakeGithubClient()),
    )
    docs = [sd async for sd in conn.discover(cursor=None)]
    uris = {d.source_uri for d in docs}
    assert "github://x/y/blob/README.md" in uris
    assert "github://x/y/blob/docs/intro.md" in uris
    assert "github://x/y/issues/1" in uris
    assert "github://x/y/pulls/2" in uris

    readme = next(d for d in docs if d.source_uri.endswith("README.md"))
    fetched = await conn.fetch(readme)
    assert fetched.data == b"bytes:x/y:README.md"

    issue = next(d for d in docs if d.source_uri.endswith("issues/1"))
    issue_body = await conn.fetch(issue)
    assert issue_body.data == b"found a bug"

    acl = await conn.acls(readme)
    assert acl.user_ids == {"alice", "bob"}


@pytest.mark.asyncio
async def test_github_delta_skips_old_issues():
    from ai_portal.rag.connectors.adapters.github import GithubConnector

    conn = await GithubConnector.setup(
        config={"scope_type": "repo", "scope_id": "x/y"},
        secret_store=_SecretStore(_FakeGithubClient()),
    )
    docs = [
        sd async for sd in conn.discover(cursor="2026-05-05T00:00:00Z")
    ]
    # Doc blobs always emitted (no updated_at), issue 1 skipped, PR 2 kept.
    assert any(d.source_uri.endswith("pulls/2") for d in docs)
    assert not any(d.source_uri.endswith("issues/1") for d in docs)
