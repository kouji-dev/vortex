"""Gitea git provider — REST API over httpx."""

from __future__ import annotations

from typing import Any

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


class GiteaProvider:
    """Gitea provider."""

    name = "gitea"

    def __init__(
        self,
        token: str,
        *,
        base_url: str,
        webhook_secret: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = token
        self._base = base_url.rstrip("/")
        self._secret = webhook_secret
        self._client = client

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self._token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _ctx(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(headers=self._headers())

    async def clone(self, repo: RepoRef, *, into: str, sandbox: Any) -> None:
        sp, sh = _sandbox_handle(sandbox)
        url = repo.clone_url.replace("https://", f"https://{self._token}@")
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
                f"{self._base}/api/v1/repos/{repo.full_name}/pulls",
                headers=self._headers(),
                json={
                    "head": head,
                    "base": base,
                    "title": ("WIP: " + title) if draft else title,
                    "body": body,
                },
            )
            r.raise_for_status()
            d = r.json()
        return self._to_pr(d, draft=draft)

    async def comment_pr(self, repo: RepoRef, pr_number: int, body: str) -> None:
        async with self._ctx() as c:
            r = await c.post(
                f"{self._base}/api/v1/repos/{repo.full_name}"
                f"/issues/{pr_number}/comments",
                headers=self._headers(),
                json={"body": body},
            )
            r.raise_for_status()

    async def read_pr(self, repo: RepoRef, pr_number: int) -> PullRequest:
        async with self._ctx() as c:
            r = await c.get(
                f"{self._base}/api/v1/repos/{repo.full_name}/pulls/{pr_number}",
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
            patch["body"] = body
        if state is not None:
            patch["state"] = state
        async with self._ctx() as c:
            r = await c.patch(
                f"{self._base}/api/v1/repos/{repo.full_name}/pulls/{pr_number}",
                headers=self._headers(),
                json=patch,
            )
            r.raise_for_status()
        return await self.read_pr(repo, pr_number)

    def parse_pr_event(
        self, payload: dict, headers: dict
    ) -> PrEventParsed | None:
        if self._secret is not None:
            if headers.get("X-Gitea-Signature") is None:
                return None
        pr = payload.get("pull_request")
        if not pr:
            return None
        repo_d = payload.get("repository", {})
        repo = RepoRef(
            repo_d.get("full_name", ""),
            repo_d.get("default_branch", "main"),
            repo_d.get("clone_url", ""),
        )
        action = payload.get("action", "")
        kind = (
            "opened"
            if action == "opened"
            else "synchronized"
            if action == "synchronized"
            else "closed"
            if action == "closed"
            else "comment"
        )
        return PrEventParsed(
            kind=kind,
            repo=repo,
            pr_number=int(pr.get("number", 0)),
            actor=payload.get("sender", {}).get("login", ""),
            body=payload.get("comment", {}).get("body"),
        )

    def _to_pr(self, d: dict, *, draft: bool | None = None) -> PullRequest:
        is_draft = (
            d.get("title", "").startswith("WIP:")
            if draft is None
            else draft
        )
        return PullRequest(
            id=str(d.get("id", "")),
            number=int(d.get("number", 0)),
            url=d.get("html_url", ""),
            state="draft" if is_draft else d.get("state", "open"),
            head_branch=d.get("head", {}).get("ref", ""),
            base_branch=d.get("base", {}).get("ref", "main"),
            title=d.get("title", ""),
            body=d.get("body") or "",
        )
