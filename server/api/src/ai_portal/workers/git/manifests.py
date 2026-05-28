"""Git provider manifests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GitManifest:
    name: str
    label: str
    auth: str  # "token" | "basic" | "pat" | "app"
    supports_webhooks: bool
    blocks_default_branch: bool


MANIFESTS: dict[str, GitManifest] = {
    "github": GitManifest("github", "GitHub", "token", True, True),
    "gitlab": GitManifest("gitlab", "GitLab", "token", True, True),
    "bitbucket": GitManifest("bitbucket", "Bitbucket", "basic", True, True),
    "gitea": GitManifest("gitea", "Gitea", "token", True, True),
    "azure_devops": GitManifest(
        "azure_devops", "Azure DevOps", "pat", True, True
    ),
}


def get(name: str) -> GitManifest:
    return MANIFESTS[name]


def all_manifests() -> list[GitManifest]:
    return list(MANIFESTS.values())
