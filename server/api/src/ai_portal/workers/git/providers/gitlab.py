"""GitLab git provider — httpx against the v4 REST API.

URL-encodes the project full path so ``group/sub/project`` repos work.
Default-branch guard matches the GitHub provider.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from ai_portal.workers.git.protocol import (
    PrEventParsed,
    PullRequest,
    RepoRef,
)
from ai_portal.workers.git.providers.github import (
    DefaultBranchPushBlocked,
    _sandbox_handle,
)

_DEFAULT_BRANCHES = {"main", "master", "trunk", "develop"}


class GitLabProvider:
    """GitLab git operations + webhook parsing."""

    name = "gitlab"

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
        return {
            "PRIVATE-TOKEN": self._token,
            "Accept": "application/json",
        }

    def _ctx(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(headers=self._headers())

    def _proj(self, repo: RepoRef) -> str:
        return quote(repo.full_name, safe="")

    async def clone(self, repo: RepoRef, *, into: str, sandbox: Any) -> None:
        sp, sh = _sandbox_handle(sandbox)
        url = repo.clone_url.replace(
            "https://", f"https://oauth2:{self._token}@"
        )
        r = await sp.exec(sh, ["git", "clone", url, into])
        if r.exit_code != 0:
            raise RuntimeError(r.stderr)

    async def branch(
        self, sandbox: Any, *, name: str, base: str | None = None
    ) -> None:
        sp, sh = _sandbox_handle(sandbox)
        if base:
            await sp.exec(sh, ["git", "checkout", base])
        r = await sp.exec(sh, ["git", "checkout", "-b", name])
        if r.exit_code != 0:
            raise RuntimeError(r.stderr)

    async def commit(
        self, sandbox: Any, *, message: str, author: tuple[str, str]
    ) -> str:
        sp, sh = _sandbox_handle(sandbox)
        name, email = author
        await sp.exec(sh, ["git", "config", "user.name", name])
        await sp.exec(sh, ["git", "config", "user.email", email])
        await sp.exec(sh, ["git", "add", "-A"])
        r = await sp.exec(sh, ["git", "commit", "-m", message])
        if r.exit_code != 0:
            raise RuntimeError(r.stderr)
        return (await sp.exec(sh, ["git", "rev-parse", "HEAD"])).stdout.strip()

    async def push(self, sandbox: Any, *, branch: str) -> None:
        if branch in _DEFAULT_BRANCHES:
            raise DefaultBranchPushBlocked(branch)
        sp, sh = _sandbox_handle(sandbox)
        r = await sp.exec(sh, ["git", "push", "-u", "origin", branch])
        if r.exit_code != 0:
            raise RuntimeError(r.stderr)

    async def create_pr(
        self,
        repo: RepoRef,
        *,
        head: str,
        base: str,
        title: str,
        body: str,
        draft: bool = True,
    ) -> PullRequest:
        if head in _DEFAULT_BRANCHES:
            raise DefaultBranchPushBlocked(head)
        async with self._ctx() as c:
            r = await c.post(
                f"{self._base}/api/v4/projects/{self._proj(repo)}/merge_requests",
                headers=self._headers(),
                json={
                    "source_branch": head,
                    "target_branch": base,
                    "title": ("Draft: " + title) if draft else title,
                    "description": body,
                    "draft": draft,
                },
            )
            r.raise_for_status()
            d = r.json()
        return self._to_pr(d, base_default=base)

    async def comment_pr(self, repo: RepoRef, pr_number: int, body: str) -> None:
        async with self._ctx() as c:
            r = await c.post(
                f"{self._base}/api/v4/projects/{self._proj(repo)}"
                f"/merge_requests/{pr_number}/notes",
                headers=self._headers(),
                json={"body": body},
            )
            r.raise_for_status()

    async def read_pr(self, repo: RepoRef, pr_number: int) -> PullRequest:
        async with self._ctx() as c:
            r = await c.get(
                f"{self._base}/api/v4/projects/{self._proj(repo)}"
                f"/merge_requests/{pr_number}",
                headers=self._headers(),
            )
            r.raise_for_status()
            d = r.json()
        return self._to_pr(d)

    async def update_pr(
        self,
        repo: RepoRef,
        pr_number: int,
        *,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        draft: bool | None = None,
    ) -> PullRequest:
        patch: dict[str, Any] = {}
        if title is not None:
            patch["title"] = title
        if body is not None:
            patch["description"] = body
        if state is not None:
            patch["state_event"] = "close" if state == "closed" else "reopen"
        if draft is not None:
            patch["draft"] = draft
        async with self._ctx() as c:
            r = await c.put(
                f"{self._base}/api/v4/projects/{self._proj(repo)}"
                f"/merge_requests/{pr_number}",
                headers=self._headers(),
                json=patch,
            )
            r.raise_for_status()
        return await self.read_pr(repo, pr_number)

    def parse_pr_event(
        self, payload: dict, headers: dict
    ) -> PrEventParsed | None:
        if self._secret is not None:
            if headers.get("X-Gitlab-Token") != self._secret:
                return None
        if payload.get("object_kind") not in ("merge_request", "note"):
            return None
        mr = payload.get("merge_request") or payload.get("object_attributes")
        if not mr:
            return None
        project = payload.get("project", {})
        repo = RepoRef(
            project.get("path_with_namespace", ""),
            project.get("default_branch", "main"),
            project.get("git_http_url", ""),
        )
        action = (mr.get("action") or mr.get("state") or "").lower()
        kind = (
            "opened"
            if action == "open"
            else "synchronized"
            if action == "update"
            else "closed"
            if action in ("close", "merged")
            else "comment"
            if payload.get("object_kind") == "note"
            else "opened"
        )
        return PrEventParsed(
            kind=kind,
            repo=repo,
            pr_number=int(mr.get("iid") or mr.get("id") or 0),
            actor=payload.get("user", {}).get("username", ""),
            body=(payload.get("object_attributes", {}) or {}).get("note"),
        )

    def _to_pr(self, d: dict, *, base_default: str = "main") -> PullRequest:
        return PullRequest(
            id=str(d.get("id", "")),
            number=int(d.get("iid", d.get("id", 0))),
            url=d.get("web_url", ""),
            state="draft"
            if d.get("draft") or d.get("work_in_progress")
            else d.get("state", "open"),
            head_branch=d.get("source_branch", ""),
            base_branch=d.get("target_branch", base_default),
            title=d.get("title", ""),
            body=d.get("description") or "",
        )
