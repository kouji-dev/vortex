"""Trigger source manifests."""

from __future__ import annotations

from dataclasses import dataclass

from ai_portal.workers.types import TriggerSourceKind


@dataclass(frozen=True)
class TriggerManifest:
    kind: TriggerSourceKind
    label: str
    description: str
    needs_secret: bool


MANIFESTS: dict[TriggerSourceKind, TriggerManifest] = {
    TriggerSourceKind.chat: TriggerManifest(
        TriggerSourceKind.chat,
        "Chat",
        "Fires when the assistant emits assign_to_worker.",
        False,
    ),
    TriggerSourceKind.rest_api: TriggerManifest(
        TriggerSourceKind.rest_api,
        "REST API",
        "Direct POST /v1/workers/tasks.",
        False,
    ),
    TriggerSourceKind.jira_webhook: TriggerManifest(
        TriggerSourceKind.jira_webhook,
        "Jira Webhook",
        "Fires when an issue is labeled with the worker label.",
        True,
    ),
    TriggerSourceKind.linear_webhook: TriggerManifest(
        TriggerSourceKind.linear_webhook,
        "Linear Webhook",
        "Fires when an issue gets the worker label.",
        True,
    ),
    TriggerSourceKind.github_issue_comment: TriggerManifest(
        TriggerSourceKind.github_issue_comment,
        "GitHub Issue Comment",
        "Fires on a comment prefixed with /worker on an issue.",
        True,
    ),
    TriggerSourceKind.github_pr_comment: TriggerManifest(
        TriggerSourceKind.github_pr_comment,
        "GitHub PR Comment",
        "Fires on a comment prefixed with /worker on a PR.",
        True,
    ),
    TriggerSourceKind.schedule_cron: TriggerManifest(
        TriggerSourceKind.schedule_cron,
        "Cron Schedule",
        "Fires on a cron schedule with a stored task template.",
        False,
    ),
}


def get(kind: TriggerSourceKind) -> TriggerManifest:
    return MANIFESTS[kind]


def all_manifests() -> list[TriggerManifest]:
    return list(MANIFESTS.values())
