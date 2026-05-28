"""Smoke tests asserting every worker protocol is importable + shaped."""

from __future__ import annotations


def test_sandbox_protocol_surface() -> None:
    from ai_portal.workers.sandboxes.protocol import (
        ExecResult,
        SandboxHandle,
        SandboxProvider,
        SnapshotRef,
    )

    for attr in (
        "provision",
        "exec",
        "stream_exec",
        "read_file",
        "write_file",
        "kill",
        "snapshot",
        "restore",
    ):
        assert hasattr(SandboxProvider, attr)

    r = ExecResult(exit_code=0, stdout="hi", stderr="", duration_ms=10, truncated=False)
    assert r.exit_code == 0

    h = SandboxHandle(id="x", provider="fake", provider_resource_id="x", workdir="/w")
    assert h.meta == {}

    s = SnapshotRef(id="s", provider="fake", size_bytes=10)
    assert s.size_bytes == 10


def test_git_protocol_surface() -> None:
    from ai_portal.workers.git.protocol import (
        GitProvider,
        PrEventParsed,
        PullRequest,
        RepoRef,
    )

    for attr in (
        "clone",
        "branch",
        "commit",
        "push",
        "create_pr",
        "comment_pr",
        "read_pr",
        "update_pr",
        "parse_pr_event",
    ):
        assert hasattr(GitProvider, attr)

    rr = RepoRef(full_name="a/b", default_branch="main", clone_url="x")
    assert rr.full_name == "a/b"

    pr = PullRequest(
        id="1",
        number=42,
        url="u",
        state="open",
        head_branch="h",
        base_branch="main",
        title="t",
        body="b",
    )
    assert pr.number == 42

    ev = PrEventParsed(kind="opened", repo=rr, pr_number=42, actor="u", body=None)
    assert ev.kind == "opened"


def test_issue_protocol_surface() -> None:
    from ai_portal.workers.issues.protocol import (
        Issue,
        IssueTracker,
        IssueWebhookEvent,
    )

    for attr in (
        "list_issues",
        "read_issue",
        "comment_issue",
        "set_status",
        "parse_webhook_event",
    ):
        assert hasattr(IssueTracker, attr)

    i = Issue(
        id="1",
        external_id="ENG-1",
        title="t",
        body="b",
        url="u",
        labels=["x"],
        status="todo",
        repo_hint=None,
    )
    ev = IssueWebhookEvent(kind="created", issue=i, actor="u", raw={})
    assert ev.kind == "created"


def test_tool_protocol_surface() -> None:
    from ai_portal.workers.tools.protocol import Tool, ToolContext, ToolResult

    assert hasattr(Tool, "invoke")
    r = ToolResult(ok=True, output={"x": 1})
    assert r.ok and r.artifacts == []

    async def _emit(*a, **kw):
        return None

    ctx = ToolContext(
        sandbox=None,
        sandbox_provider=None,
        task_id="t",
        run_id="r",
        actor_id="a",
        org_id="o",
        emit_event=_emit,
    )
    assert ctx.pool_settings == {}


def test_agent_loop_protocol_surface() -> None:
    from ai_portal.workers.agent_loops.protocol import AgentLoop, AgentRunCtx

    assert hasattr(AgentLoop, "run")
    c = AgentRunCtx(
        task=None,
        run=None,
        tools=[],
        gateway=None,
        sandbox=None,
        sandbox_provider=None,
        repo=None,
        model="claude-sonnet-4-6",
    )
    assert c.max_iterations == 40


def test_trigger_source_protocol_surface() -> None:
    from ai_portal.workers.triggers.protocol import TriggerSource

    assert hasattr(TriggerSource, "parse")
