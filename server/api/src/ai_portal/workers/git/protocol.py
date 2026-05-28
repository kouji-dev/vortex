"""Git provider protocol — pluggable VCS backend.

Concrete providers (github, gitlab, bitbucket, gitea, azure_devops) implement
this contract. The orchestrator only talks to ``GitProvider``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class RepoRef:
    """Lightweight ref to a repository."""

    full_name: str
    default_branch: str
    clone_url: str


@dataclass
class PullRequest:
    """Provider-agnostic PR snapshot."""

    id: str
    number: int
    url: str
    state: str
    head_branch: str
    base_branch: str
    title: str
    body: str


@dataclass
class PrEventParsed:
    """Parsed PR webhook payload."""

    kind: str
    repo: RepoRef
    pr_number: int
    actor: str
    body: str | None


@runtime_checkable
class GitProvider(Protocol):
    """Contract every git backend must satisfy."""

    name: str

    async def clone(self, repo: RepoRef, *, into: str, sandbox: Any) -> None: ...

    async def branch(
        self, sandbox: Any, *, name: str, base: str | None = None
    ) -> None: ...

    async def commit(
        self, sandbox: Any, *, message: str, author: tuple[str, str]
    ) -> str: ...

    async def push(self, sandbox: Any, *, branch: str) -> None: ...

    async def create_pr(
        self,
        repo: RepoRef,
        *,
        head: str,
        base: str,
        title: str,
        body: str,
        draft: bool = True,
    ) -> PullRequest: ...

    async def comment_pr(
        self, repo: RepoRef, pr_number: int, body: str
    ) -> None: ...

    async def read_pr(self, repo: RepoRef, pr_number: int) -> PullRequest: ...

    async def update_pr(
        self,
        repo: RepoRef,
        pr_number: int,
        *,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        draft: bool | None = None,
    ) -> PullRequest: ...

    def parse_pr_event(
        self, payload: dict, headers: dict
    ) -> PrEventParsed | None: ...
