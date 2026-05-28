"""Jira Cloud issue tracker — REST v3 over httpx.

Basic auth with ``email:api_token``. Webhook signature verification is
left to the deployment layer (Jira's HMAC-signed webhooks are opt-in).
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from ai_portal.workers.issues.protocol import Issue, IssueWebhookEvent


class JiraCloudTracker:
    """Atlassian Jira Cloud tracker."""

    name = "jira_cloud"

    def __init__(
        self,
        *,
        site: str,
        email: str,
        token: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._site = site.rstrip("/")
        auth = base64.b64encode(f"{email}:{token}".encode()).decode()
        self._headers_d = {
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self._client = client

    def _ctx(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(headers=self._headers_d)

    async def list_issues(
        self, *, project: str, query: str | None = None
    ) -> list[Issue]:
        jql = f"project={project}"
        if query:
            jql += f" AND {query}"
        async with self._ctx() as c:
            r = await c.get(
                f"{self._site}/rest/api/3/search",
                headers=self._headers_d,
                params={"jql": jql},
            )
            r.raise_for_status()
            d = r.json()
        return [self._to_issue(x) for x in d.get("issues", [])]

    async def read_issue(self, *, project: str, external_id: str) -> Issue:
        async with self._ctx() as c:
            r = await c.get(
                f"{self._site}/rest/api/3/issue/{external_id}",
                headers=self._headers_d,
            )
            r.raise_for_status()
            d = r.json()
        return self._to_issue(d)

    async def comment_issue(
        self, *, project: str, external_id: str, body: str
    ) -> None:
        async with self._ctx() as c:
            r = await c.post(
                f"{self._site}/rest/api/3/issue/{external_id}/comment",
                headers=self._headers_d,
                json={"body": body},
            )
            r.raise_for_status()

    async def set_status(
        self, *, project: str, external_id: str, status: str
    ) -> None:
        async with self._ctx() as c:
            tr = await c.get(
                f"{self._site}/rest/api/3/issue/{external_id}/transitions",
                headers=self._headers_d,
            )
            tr.raise_for_status()
            transitions = tr.json().get("transitions", [])
            t = next(
                (t for t in transitions if t["name"].lower() == status.lower()),
                None,
            )
            if not t:
                raise ValueError(f"no transition for {status}")
            r = await c.post(
                f"{self._site}/rest/api/3/issue/{external_id}/transitions",
                headers=self._headers_d,
                json={"transition": {"id": t["id"]}},
            )
            r.raise_for_status()

    def parse_webhook_event(
        self, payload: dict, headers: dict
    ) -> IssueWebhookEvent | None:
        if "issue" not in payload:
            return None
        issue = self._to_issue(payload["issue"])
        ev = payload.get("webhookEvent", "")
        items = payload.get("changelog", {}).get("items", [])
        labeled = any(item.get("field") == "labels" for item in items)
        kind = (
            "labeled"
            if labeled
            else "created"
            if "created" in ev
            else "status_changed"
            if "updated" in ev
            else "commented"
        )
        return IssueWebhookEvent(
            kind=kind,
            issue=issue,
            actor=payload.get("user", {}).get("displayName", ""),
            raw=payload,
        )

    def _to_issue(self, raw: dict) -> Issue:
        f = raw.get("fields", {}) or {}
        status = f.get("status") or {}
        return Issue(
            id=str(raw.get("id", "")),
            external_id=raw.get("key", ""),
            title=f.get("summary", "") or "",
            body=str(f.get("description") or ""),
            url=f"{self._site}/browse/{raw.get('key', '')}",
            labels=list(f.get("labels", []) or []),
            status=status.get("name", "") or "",
            repo_hint=None,
        )
