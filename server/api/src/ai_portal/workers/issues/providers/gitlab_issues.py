"""GitLab Issues tracker — REST v4."""

from __future__ import annotations

from urllib.parse import quote

import httpx

from ai_portal.workers.issues.protocol import Issue, IssueWebhookEvent


class GitLabIssuesTracker:
    """GitLab issues tracker."""

    name = "gitlab_issues"

    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://gitlab.com",
        webhook_secret: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = token
        self._base = base_url.rstrip("/")
        self._secret = webhook_secret
        self._client = client

    def _headers(self) -> dict[str, str]:
        return {"PRIVATE-TOKEN": self._token, "Accept": "application/json"}

    def _ctx(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(headers=self._headers())

    def _proj(self, project: str) -> str:
        return quote(project, safe="")

    async def list_issues(
        self, *, project: str, query: str | None = None
    ) -> list[Issue]:
        params: dict[str, str] = {"state": "opened"}
        if query:
            params["labels"] = query
        async with self._ctx() as c:
            r = await c.get(
                f"{self._base}/api/v4/projects/{self._proj(project)}/issues",
                headers=self._headers(),
                params=params,
            )
            r.raise_for_status()
        return [self._to_issue(x, project) for x in r.json()]

    async def read_issue(self, *, project: str, external_id: str) -> Issue:
        async with self._ctx() as c:
            r = await c.get(
                f"{self._base}/api/v4/projects/{self._proj(project)}"
                f"/issues/{external_id}",
                headers=self._headers(),
            )
            r.raise_for_status()
        return self._to_issue(r.json(), project)

    async def comment_issue(
        self, *, project: str, external_id: str, body: str
    ) -> None:
        async with self._ctx() as c:
            r = await c.post(
                f"{self._base}/api/v4/projects/{self._proj(project)}"
                f"/issues/{external_id}/notes",
                headers=self._headers(),
                json={"body": body},
            )
            r.raise_for_status()

    async def set_status(
        self, *, project: str, external_id: str, status: str
    ) -> None:
        event = "close" if status.lower() in ("closed", "done") else "reopen"
        async with self._ctx() as c:
            r = await c.put(
                f"{self._base}/api/v4/projects/{self._proj(project)}"
                f"/issues/{external_id}",
                headers=self._headers(),
                json={"state_event": event},
            )
            r.raise_for_status()

    def parse_webhook_event(
        self, payload: dict, headers: dict
    ) -> IssueWebhookEvent | None:
        if self._secret is not None and headers.get("X-Gitlab-Token") != self._secret:
            return None
        if payload.get("object_kind") != "issue":
            return None
        attrs = payload.get("object_attributes", {})
        project = payload.get("project", {}).get("path_with_namespace", "")
        action = attrs.get("action", "open")
        kind = (
            "created"
            if action == "open"
            else "status_changed"
            if action in ("close", "reopen")
            else "labeled"
            if "labels" in (payload.get("changes") or {})
            else "commented"
        )
        return IssueWebhookEvent(
            kind=kind,
            issue=self._to_issue(attrs, project),
            actor=payload.get("user", {}).get("username", ""),
            raw=payload,
        )

    def _to_issue(self, raw: dict, project: str) -> Issue:
        labels = raw.get("labels", []) or []
        if labels and isinstance(labels[0], dict):
            labels = [lbl.get("title", "") for lbl in labels]
        return Issue(
            id=str(raw.get("id", "")),
            external_id=str(raw.get("iid", raw.get("id", ""))),
            title=raw.get("title", ""),
            body=raw.get("description") or "",
            url=raw.get("web_url", "") or raw.get("url", ""),
            labels=list(labels),
            status=raw.get("state", ""),
            repo_hint=project or None,
        )
