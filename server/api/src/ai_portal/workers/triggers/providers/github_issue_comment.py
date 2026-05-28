"""GitHub issue-comment trigger — fires on ``/worker`` (configurable) phrase."""

from __future__ import annotations

from ai_portal.workers.triggers.protocol import TriggerSource  # noqa: F401
from ai_portal.workers.types import TaskInput, TriggerSourceKind


class GitHubIssueCommentTrigger:
    """Trigger on issue comments starting with a phrase (default ``/worker``)."""

    kind = TriggerSourceKind.github_issue_comment

    def __init__(self, *, phrase: str = "/worker") -> None:
        self._phrase = phrase

    def parse(
        self, payload: dict, headers: dict | None = None
    ) -> TaskInput | None:
        comment = (payload.get("comment") or {}).get("body", "") or ""
        if not comment.startswith(self._phrase):
            return None
        issue = payload.get("issue") or {}
        # Skip PR-comment payloads which also include ``pull_request``.
        if "pull_request" in issue:
            return None
        repo_obj = payload.get("repository") or {}
        repo = repo_obj.get("full_name")
        if not repo:
            return None
        instruction = comment[len(self._phrase):].strip()
        return TaskInput(
            title=instruction[:200] or issue.get("title", "Worker task"),
            description=(
                f"From issue #{issue.get('number')} comment:\n\n"
                f"{instruction}\n\n---\nIssue body:\n{issue.get('body', '')}"
            ),
            repo=repo,
            base_branch=repo_obj.get("default_branch", "main"),
            extra={
                "issue_number": issue.get("number"),
                "comment_id": (payload.get("comment") or {}).get("id"),
                "source": "github_issue_comment",
            },
        )
