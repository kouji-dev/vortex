"""jira connector — issues + attachments via a fake client."""

from __future__ import annotations

import pytest


class _FakeJiraClient:
    async def list_issues(self, project_key):
        return [
            {
                "key": "PROJ-1",
                "id": "10001",
                "fields": {
                    "summary": "first issue",
                    "description": "body 1",
                    "updated": "2026-05-01T00:00:00.000+0000",
                    "attachment": [
                        {
                            "id": "att1",
                            "filename": "spec.pdf",
                            "mimeType": "application/pdf",
                            "size": 12,
                        }
                    ],
                    "comment": {
                        "comments": [{"body": "c1"}],
                    },
                },
            },
            {
                "key": "PROJ-2",
                "id": "10002",
                "fields": {
                    "summary": "second issue",
                    "description": "body 2",
                    "updated": "2026-05-10T00:00:00.000+0000",
                },
            },
        ]

    async def get_attachment_bytes(self, attachment_id):
        return f"bytes:{attachment_id}".encode()

    async def list_project_users(self, project_key):
        return ["acc-1", "acc-2"]


class _SecretStore:
    def __init__(self, client):
        self.jira_client = client


@pytest.mark.asyncio
async def test_jira_discover_with_attachments_and_acls():
    from ai_portal.rag.connectors.adapters.jira import JiraConnector

    conn = await JiraConnector.setup(
        config={"base_url": "https://x.atlassian.net", "project_key": "PROJ"},
        secret_store=_SecretStore(_FakeJiraClient()),
    )
    docs = [sd async for sd in conn.discover(cursor=None)]
    uris = {d.source_uri for d in docs}
    assert "jira://PROJ/PROJ-1" in uris
    assert "jira://PROJ/PROJ-2" in uris
    assert "jira://PROJ/PROJ-1/attachments/att1" in uris

    issue = next(d for d in docs if d.source_uri == "jira://PROJ/PROJ-1")
    fetched = await conn.fetch(issue)
    assert b"body 1" in fetched.data
    assert b"c1" in fetched.data  # comment appended

    att = next(d for d in docs if "/attachments/" in d.source_uri)
    att_fetched = await conn.fetch(att)
    assert att_fetched.data == b"bytes:att1"

    acl = await conn.acls(issue)
    assert acl.user_ids == {"acc-1", "acc-2"}


@pytest.mark.asyncio
async def test_jira_delta_skips_old_issues():
    from ai_portal.rag.connectors.adapters.jira import JiraConnector

    conn = await JiraConnector.setup(
        config={"base_url": "x", "project_key": "PROJ", "include_attachments": False},
        secret_store=_SecretStore(_FakeJiraClient()),
    )
    docs = [
        sd
        async for sd in conn.discover(cursor="2026-05-05T00:00:00.000+0000")
    ]
    assert [d.source_uri for d in docs] == ["jira://PROJ/PROJ-2"]
