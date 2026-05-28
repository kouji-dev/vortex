"""Canonical worker types + lifecycle state machine.

Defines:
- ``TaskStatus`` — lifecycle phases.
- ``TriggerSourceKind`` — where a task came from.
- ``EventKind`` — stream-event taxonomy.
- ``ApprovalKind`` / ``ApprovalPolicy`` — approval gates.
- ``TaskInput`` — payload to submit a task.
- ``RunState`` — in-memory snapshot of a run.
- ``WorkerEvent`` — per-run event row (data, not ORM).
- ``ResourceLimits`` — sandbox resource caps.
- ``can_transition()`` — guard for the state machine.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class TaskStatus(str, enum.Enum):
    queued = "queued"
    planning = "planning"
    awaiting_plan_approval = "awaiting_plan_approval"
    executing = "executing"
    awaiting_pr_approval = "awaiting_pr_approval"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    paused = "paused"


class TriggerSourceKind(str, enum.Enum):
    chat = "chat"
    rest_api = "rest_api"
    jira_webhook = "jira_webhook"
    linear_webhook = "linear_webhook"
    github_issue_comment = "github_issue_comment"
    github_pr_comment = "github_pr_comment"
    schedule_cron = "schedule_cron"


class EventKind(str, enum.Enum):
    agent_thought = "agent_thought"
    tool_call = "tool_call"
    tool_result = "tool_result"
    file_changed = "file_changed"
    shell_output = "shell_output"
    pr_created = "pr_created"
    error = "error"
    phase_changed = "phase_changed"
    approval_requested = "approval_requested"
    user_message = "user_message"
    cost_update = "cost_update"
    egress_blocked = "egress_blocked"
    secret_blocked = "secret_blocked"


class ApprovalKind(str, enum.Enum):
    plan = "plan"
    pr = "pr"
    budget = "budget"


class ApprovalPolicy(str, enum.Enum):
    always = "always"
    never = "never"
    on_cost_above = "on_cost_above"
    on_files_matching = "on_files_matching"
    on_first_run_for_repo = "on_first_run_for_repo"


@dataclass
class TaskInput:
    title: str
    description: str
    repo: str
    base_branch: str = "main"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkerEvent:
    run_id: str
    kind: EventKind
    payload: dict[str, Any]
    ts: datetime


@dataclass
class ResourceLimits:
    cpu_cores: float = 2.0
    ram_mb: int = 4096
    disk_mb: int = 10240
    wall_time_sec: int = 3600
    max_processes: int = 256


@dataclass
class RunState:
    """Live snapshot of a worker run held in orchestrator memory."""

    run_id: str
    task_id: str
    status: TaskStatus
    attempt_no: int
    cost_cents: int = 0
    sandbox_id: str | None = None
    started_at: datetime | None = None
    error: str | None = None


_LEGAL: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.queued: {
        TaskStatus.planning,
        TaskStatus.cancelled,
        TaskStatus.failed,
    },
    TaskStatus.planning: {
        TaskStatus.awaiting_plan_approval,
        TaskStatus.executing,
        TaskStatus.failed,
        TaskStatus.cancelled,
    },
    TaskStatus.awaiting_plan_approval: {
        TaskStatus.executing,
        TaskStatus.cancelled,
        TaskStatus.failed,
    },
    TaskStatus.executing: {
        TaskStatus.awaiting_pr_approval,
        TaskStatus.completed,
        TaskStatus.failed,
        TaskStatus.cancelled,
        TaskStatus.paused,
    },
    TaskStatus.paused: {
        TaskStatus.executing,
        TaskStatus.cancelled,
        TaskStatus.failed,
    },
    TaskStatus.awaiting_pr_approval: {
        TaskStatus.completed,
        TaskStatus.cancelled,
        TaskStatus.failed,
    },
    TaskStatus.completed: set(),
    TaskStatus.failed: set(),
    TaskStatus.cancelled: set(),
}


def can_transition(a: TaskStatus, b: TaskStatus) -> bool:
    """True iff ``a -> b`` is a legal state transition."""
    return b in _LEGAL.get(a, set())
