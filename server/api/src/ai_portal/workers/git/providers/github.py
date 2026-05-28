"""GitHub git provider — full exemplar.

Uses raw httpx against the v3 REST API rather than PyGithub directly so
the client is fully async and easy to mock with respx. PyGithub is still
listed as a dep so consumers wanting the higher-level API can use it.

Guards against pushing or PR-ing into protected default branches
(``main``, ``master``, ``trunk``, ``develop``).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import httpx

from ai_portal.workers.git.pr_templates import PrTemplate, apply_template
from ai_portal.workers.git.protocol import (
    PrEventParsed,
    PullRequest,
    RepoRef,
)

_DEFAULT_BRANCHES = {"main", "master", "trunk", "develop"}


class DefaultBranchPushBlocked(Exception):
    """Raised when an operation would push or PR into a protected branch."""

    def __init__(self, branch: str) -> None:
        super().__init__(f"refusing to push/pr to protected branch: {branch}")
        self.branch = branch


def _sandbox_handle(sandbox: Any) -> tuple[Any, Any]:
    """Accept either a ``{"provider","handle"}`` dict or an object with attrs."""
    if isinstance(sandbox, dict):
        return sandbox["provider"], sandbox["handle"]
    return sandbox.provider, sandbox.handle


class GitHubProvider:
    """GitHub git operations + webhook parsing."""

    name = "github"
    base = "https://api.github.com"

    def __init__(
        self,
        token: str,
        *,
        app_id: str | None = None,
        webhook_secret: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = token
        self._app_id = app_id
        self._secret = webhook_secret.encode() if webhook_secret else None
        self._client = client

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _ctx(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(headers=self._headers())

    # ---------------- git plumbing (in-sandbox) ----------------

    async def clone(self, repo: RepoRef, *, into: str, sandbox: Any) -> None:
        sp, sh = _sandbox_handle(sandbox)
        url = repo.clone_url.replace(
            "https://", f"https://x-access-token:{self._token}@"
        )
        r = await sp.exec(sh, ["git", "clone", url, into], timeout_sec=600)
        if r.exit_code != 0:
            raise RuntimeError(f"clone failed: {r.stderr}")

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
        sha = (await sp.exec(sh, ["git", "rev-parse", "HEAD"])).stdout.strip()
        return sha

    async def push(self, sandbox: Any, *, branch: str) -> None:
        if branch in _DEFAULT_BRANCHES:
            raise DefaultBranchPushBlocked(branch)
        sp, sh = _sandbox_handle(sandbox)
        r = await sp.exec(sh, ["git", "push", "-u", "origin", branch])
        if r.exit_code != 0:
            raise RuntimeError(r.stderr)

    # ---------------- REST API ----------------

    async def create_pr(
        self,
        repo: RepoRef,
        *,
        head: str,
        base: str,
        title: str,
        body: str,
        draft: bool = True,
        template: PrTemplate | None = None,
        task_id: str = "",
        summary: str = "",
    ) -> PullRequest:
        if head in _DEFAULT_BRANCHES:
            raise DefaultBranchPushBlocked(head)
        formatted = apply_template(
            template,
            title=title,
            body=body,
            task_id=task_id,
            branch=head,
            repo=repo.full_name,
            summary=summary or body,
        )
        async with self._ctx() as c:
            r = await c.post(
                f"{self.base}/repos/{repo.full_name}/pulls",
                headers=self._headers(),
                json={
                    "head": head,
                    "base": base,
                    "title": formatted["title"],
                    "body": formatted["body"],
                    "draft": draft,
                },
            )
            r.raise_for_status()
            d = r.json()
        return self._to_pr(d)

    async def comment_pr(self, repo: RepoRef, pr_number: int, body: str) -> None:
        async with self._ctx() as c:
            r = await c.post(
                f"{self.base}/repos/{repo.full_name}/issues/{pr_number}/comments",
                headers=self._headers(),
                json={"body": body},
            )
            r.raise_for_status()

    async def read_pr(self, repo: RepoRef, pr_number: int) -> PullRequest:
        async with self._ctx() as c:
            r = await c.get(
                f"{self.base}/repos/{repo.full_name}/pulls/{pr_number}",
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
        if draft is not None:
            patch["draft"] = draft
        async with self._ctx() as c:
            r = await c.patch(
                f"{self.base}/repos/{repo.full_name}/pulls/{pr_number}",
                headers=self._headers(),
                json=patch,
            )
            r.raise_for_status()
        return await self.read_pr(repo, pr_number)

    # ---------------- webhook parsing ----------------

    def parse_pr_event(
        self, payload: dict, headers: dict
    ) -> PrEventParsed | None:
        if self._secret is not None:
            sig = headers.get("X-Hub-Signature-256", "")
            mac = "sha256=" + hmac.new(
                self._secret,
                msg=json.dumps(payload, separators=(",", ":")).encode(),
                digestmod=hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(mac, sig):
                return None
        action = payload.get("action")
        if "pull_request" not in payload and "issue" not in payload:
            return None
        if "pull_request" in payload:
            pr = payload["pull_request"]
            repo = payload["repository"]
            kind = (
                "opened"
                if action == "opened"
                else "synchronized"
                if action == "synchronize"
                else "closed"
                if action == "closed"
                else "comment"
            )
            return PrEventParsed(
                kind=kind,
                repo=RepoRef(
                    repo["full_name"], repo["default_branch"], repo["clone_url"]
                ),
                pr_number=pr["number"],
                actor=payload["sender"]["login"],
                body=payload.get("comment", {}).get("body"),
            )
        return None

    # ---------------- helpers ----------------

    def _to_pr(self, d: dict) -> PullRequest:
        return PullRequest(
            id=str(d["id"]),
            number=d["number"],
            url=d["html_url"],
            state="draft" if d.get("draft") else d["state"],
            head_branch=d["head"]["ref"],
            base_branch=d["base"]["ref"],
            title=d["title"],
            body=d.get("body") or "",
        )
