"""GitHub Issues tracker — reuses GitHub REST + auth."""

from __future__ import annotations

import httpx

from ai_portal.workers.issues.protocol import Issue, IssueWebhookEvent


class GitHubIssuesTracker:
    """GitHub Issues — backed by the same v3 REST API."""

    name = "github_issues"
    base = "https://api.github.com"

    def __init__(
        self,
        token: str,
        *,
        webhook_secret: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = token
        self._secret = webhook_secret
        self._client = client

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _ctx(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(headers=self._headers())

    async def list_issues(
        self, *, project: str, query: str | None = None
    ) -> list[Issue]:
        params: dict[str, str] = {"state": "open"}
        if query:
            params["labels"] = query
        async with self._ctx() as c:
            r = await c.get(
                f"{self.base}/repos/{project}/issues",
                headers=self._headers(),
                params=params,
            )
            r.raise_for_status()
            return [self._to_issue(x, project) for x in r.json() if "pull_request" not in x]

    async def read_issue(self, *, project: str, external_id: str) -> Issue:
        async with self._ctx() as c:
            r = await c.get(
                f"{self.base}/repos/{project}/issues/{external_id}",
                headers=self._headers(),
            )
            r.raise_for_status()
        return self._to_issue(r.json(), project)

    async def comment_issue(
        self, *, project: str, external_id: str, body: str
    ) -> None:
        async with self._ctx() as c:
            r = await c.post(
                f"{self.base}/repos/{project}/issues/{external_id}/comments",
                headers=self._headers(),
                json={"body": body},
            )
            r.raise_for_status()

    async def set_status(
        self, *, project: str, external_id: str, status: str
    ) -> None:
        github_state = "closed" if status.lower() in ("done", "closed", "resolved") else "open"
        async with self._ctx() as c:
            r = await c.patch(
                f"{self.base}/repos/{project}/issues/{external_id}",
                headers=self._headers(),
                json={"state": github_state},
            )
            r.raise_for_status()

    def parse_webhook_event(
        self, payload: dict, headers: dict
    ) -> IssueWebhookEvent | None:
        if "issue" not in payload or "pull_request" in payload.get("issue", {}):
            return None
        action = payload.get("action", "")
        kind = (
            "labeled"
            if action == "labeled"
            else "created"
            if action == "opened"
            else "status_changed"
            if action in ("closed", "reopened")
            else "commented"
            if action == "created" and "comment" in payload
            else action or "status_changed"
        )
        repo = payload.get("repository", {})
        return IssueWebhookEvent(
            kind=kind,
            issue=self._to_issue(
                payload["issue"], repo.get("full_name", "")
            ),
            actor=payload.get("sender", {}).get("login", ""),
            raw=payload,
        )

    def _to_issue(self, raw: dict, project: str) -> Issue:
        labels = [
            label["name"] if isinstance(label, dict) else str(label)
            for label in raw.get("labels", []) or []
        ]
        return Issue(
            id=str(raw.get("id", "")),
            external_id=str(raw.get("number", "")),
            title=raw.get("title", ""),
            body=raw.get("body") or "",
            url=raw.get("html_url", ""),
            labels=labels,
            status=raw.get("state", ""),
            repo_hint=project or None,
        )
