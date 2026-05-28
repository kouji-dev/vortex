"""Tests for replay input builder."""

from __future__ import annotations

from ai_portal.workers.replay.service import build_replay_input


class _Row:
    def __init__(self, **kw):
        self.id = kw.get("id", "task-1")
        self.org_id = kw.get("org_id", "org-1")
        self.pool_id = kw.get("pool_id", "pool-1")
        self.title = kw.get("title", "fix")
        self.description = kw.get("description", "the bug")
        self.repo = kw.get("repo", "acme/api")
        self.base_branch = kw.get("base_branch", "main")
        self.trigger_source = kw.get("trigger_source", "rest_api")
        self.trigger_payload_json = kw.get("trigger_payload_json", {})


def test_builds_task_input_from_row() -> None:
    out = build_replay_input(task_row=_Row())
    assert out.task_input.title == "fix"
    assert out.task_input.repo == "acme/api"
    assert out.task_input.base_branch == "main"
    assert out.parent_task_id == "task-1"
    assert out.org_id == "org-1"
    assert out.pool_id == "pool-1"


def test_stamps_replay_of_marker() -> None:
    out = build_replay_input(task_row=_Row())
    assert out.task_input.extra["replay_of"] == "task-1"


def test_stamps_actor_id_when_provided() -> None:
    out = build_replay_input(task_row=_Row(), actor_id="alice")
    assert out.task_input.extra["replay_actor_id"] == "alice"


def test_carries_forward_original_trigger_payload() -> None:
    row = _Row(trigger_payload_json={"github_pr": 42, "issue": 7})
    out = build_replay_input(task_row=row)
    assert out.task_input.extra["github_pr"] == 42
    assert out.task_input.extra["issue"] == 7
    assert out.task_input.extra["replay_of"] == "task-1"


def test_defaults_base_branch_when_missing() -> None:
    row = _Row(base_branch=None)
    out = build_replay_input(task_row=row)
    assert out.task_input.base_branch == "main"
