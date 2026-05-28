"""Issue-tracker manifests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IssueManifest:
    name: str
    label: str
    auth: str
    supports_webhooks: bool
    deployment: str  # "managed" | "self-hosted"


MANIFESTS: dict[str, IssueManifest] = {
    "jira_cloud": IssueManifest(
        "jira_cloud", "Jira Cloud", "basic_email_token", True, "managed"
    ),
    "linear": IssueManifest(
        "linear", "Linear", "api_key", True, "managed"
    ),
    "github_issues": IssueManifest(
        "github_issues", "GitHub Issues", "token", True, "managed"
    ),
    "gitlab_issues": IssueManifest(
        "gitlab_issues", "GitLab Issues", "token", True, "self-hosted"
    ),
    "azure_boards": IssueManifest(
        "azure_boards", "Azure Boards", "pat", True, "managed"
    ),
}


def get(name: str) -> IssueManifest:
    return MANIFESTS[name]


def all_manifests() -> list[IssueManifest]:
    return list(MANIFESTS.values())
