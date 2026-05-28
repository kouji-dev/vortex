"""Tests for worker canonical types + state machine."""

from __future__ import annotations

from datetime import datetime

from ai_portal.workers.types import (
    ApprovalKind,
    ApprovalPolicy,
    EventKind,
    ResourceLimits,
    RunState,
    TaskInput,
    TaskStatus,
    TriggerSourceKind,
    WorkerEvent,
    can_transition,
)


def test_status_transitions_legal() -> None:
    assert can_transition(TaskStatus.queued, TaskStatus.planning)
    assert can_transition(TaskStatus.planning, TaskStatus.awaiting_plan_approval)
    assert can_transition(TaskStatus.awaiting_plan_approval, TaskStatus.executing)
    assert can_transition(TaskStatus.executing, TaskStatus.awaiting_pr_approval)
    assert can_transition(TaskStatus.executing, TaskStatus.completed)
    assert can_transition(TaskStatus.executing, TaskStatus.failed)
    assert can_transition(TaskStatus.executing, TaskStatus.cancelled)
    assert can_transition(TaskStatus.executing, TaskStatus.paused)
    assert can_transition(TaskStatus.paused, TaskStatus.executing)


def test_status_transitions_illegal() -> None:
    assert not can_transition(TaskStatus.completed, TaskStatus.executing)
    assert not can_transition(TaskStatus.cancelled, TaskStatus.executing)
    assert not can_transition(TaskStatus.failed, TaskStatus.executing)
    assert not can_transition(TaskStatus.queued, TaskStatus.completed)
    assert not can_transition(TaskStatus.queued, TaskStatus.executing)


def test_task_input_defaults() -> None:
    ti = TaskInput(title="t", description="d", repo="acme/api")
    assert ti.base_branch == "main"
    assert ti.extra == {}


def test_resource_limits_defaults() -> None:
    r = ResourceLimits()
    assert r.cpu_cores == 2.0
    assert r.ram_mb == 4096
    assert r.disk_mb == 10240
    assert r.wall_time_sec == 3600
    assert r.max_processes == 256


def test_worker_event_shape() -> None:
    ev = WorkerEvent(
        run_id="r1",
        kind=EventKind.agent_thought,
        payload={"text": "hi"},
        ts=datetime.utcnow(),
    )
    assert ev.run_id == "r1"
    assert ev.kind is EventKind.agent_thought


def test_run_state_defaults() -> None:
    rs = RunState(
        run_id="r1",
        task_id="t1",
        status=TaskStatus.queued,
        attempt_no=1,
    )
    assert rs.cost_cents == 0
    assert rs.sandbox_id is None


def test_enums_have_expected_members() -> None:
    assert TriggerSourceKind.chat.value == "chat"
    assert TriggerSourceKind.schedule_cron.value == "schedule_cron"
    assert ApprovalKind.plan.value == "plan"
    assert ApprovalPolicy.on_cost_above.value == "on_cost_above"
    assert EventKind.egress_blocked.value == "egress_blocked"
    assert EventKind.secret_blocked.value == "secret_blocked"
