"""GitHub PR-comment trigger — same shape as issue_comment but PR-scoped."""

from __future__ import annotations

from ai_portal.workers.triggers.protocol import TriggerSource  # noqa: F401
from ai_portal.workers.types import TaskInput, TriggerSourceKind


class GitHubPrCommentTrigger:
    """Trigger on PR review or issue comments on PRs starting with a phrase."""

    kind = TriggerSourceKind.github_pr_comment

    def __init__(self, *, phrase: str = "/worker") -> None:
        self._phrase = phrase

    def parse(
        self, payload: dict, headers: dict | None = None
    ) -> TaskInput | None:
        comment = (payload.get("comment") or {}).get("body", "") or ""
        if not comment.startswith(self._phrase):
            return None
        # GitHub PR comments arrive as ``issue_comment`` events where the
        # issue payload includes ``pull_request``; ``pull_request_review_comment``
        # carries ``pull_request`` directly.
        issue = payload.get("issue") or {}
        pr = payload.get("pull_request") or issue.get("pull_request") or {}
        pr_number = (
            issue.get("number")
            if "pull_request" in issue
            else pr.get("number")
        )
        if not pr_number:
            return None
        repo_obj = payload.get("repository") or {}
        repo = repo_obj.get("full_name")
        if not repo:
            return None
        instruction = comment[len(self._phrase):].strip()
        return TaskInput(
            title=instruction[:200] or f"PR #{pr_number} task",
            description=(
                f"From PR #{pr_number} comment:\n\n{instruction}"
            ),
            repo=repo,
            base_branch=repo_obj.get("default_branch", "main"),
            extra={
                "pr_number": pr_number,
                "comment_id": (payload.get("comment") or {}).get("id"),
                "source": "github_pr_comment",
            },
        )
