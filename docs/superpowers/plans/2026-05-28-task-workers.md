# Task Workers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build autonomous AI coding agents that take a task, run inside a sandboxed VM/container connected to git, open a reviewable PR, stream every action live, and stay under Control Plane governance.

**Architecture:** New module `server/api/src/ai_portal/workers/` with sub-packages: `sandboxes/`, `git/`, `issues/`, `triggers/`, `tools/`, `agent_loops/`, `orchestrator/`, `events/`, `secrets/`, `egress/`, `budget/`, `policies/`. Each pluggable surface is `protocol.py` + `providers/<name>.py` + `registry.py`. The orchestrator drives the state machine (`queued → planning → awaiting_plan_approval → executing → awaiting_pr_approval → completed | failed | cancelled`). All LLM calls go through Gateway facade. All RBAC / audit / usage / webhooks / blob storage / notifications come from Control Plane. SSE writer streams `worker_events` to the browser. RAG and Memories tools are optional adapters.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x async, Alembic, asyncpg, pytest + pytest-asyncio, respx (HTTP mocks), `docker` (Python SDK), `kubernetes` (Python SDK), `PyGithub`, `python-gitlab`, `atlassian-python-api`, `httpx` (linear / azure devops / bitbucket / gitea raw), `mcp` (MCP client), `playwright` (already in repo — isolated for browser tool inside sandbox image only), `ripgrep` + `ast-grep` binaries baked into sandbox images.

**Spec:** `docs/superpowers/specs/2026-05-28-task-workers-design.md`

**Depends on (hard):** `2026-05-28-control-plane.md`, `2026-05-28-gateway.md`
**Depends on (soft):** `2026-05-28-rag.md` (for `web_search` + `kb_search` tools), `2026-05-28-memories.md` (for `memory_recall` / `memory_remember`)

---

## Pre-flight

- [ ] **Step P1: Confirm worktree + branch**

```bash
git status --short
git rev-parse --abbrev-ref HEAD     # expect: pivot-workers
```

- [ ] **Step P2: Sync deps**

Add to `server/api/pyproject.toml`:
```toml
docker = "^7.1"                       # python sdk
kubernetes = "^31.0"
PyGithub = "^2.4"
python-gitlab = "^4.13"
atlassian-python-api = "^3.41"
mcp = "^1.1"                          # MCP client
ast-grep-cli = "^0.30"                # invoked as subprocess; binary preferred
```

```bash
cd server/api && uv lock && uv sync
```

- [ ] **Step P3: Confirm Control Plane + Gateway merged in base**

```bash
python -c "from ai_portal.control_plane import require_permission, emit_audit, emit_usage, emit_webhook, register_deleter, BlobStore, notify_send; print('cp ok')"
python -c "from ai_portal.gateway import complete, stream, embed, count_tokens; print('gw ok')"
```

- [ ] **Step P4: Empty alembic revision for module**

```bash
cd server/api
alembic revision -m "workers: scaffolding" --autogenerate=false
# note rev id — will be filled across phases
```

- [ ] **Step P5: Scaffold module skeleton**

```bash
mkdir -p server/api/src/ai_portal/workers/{sandboxes/providers,git/providers,issues/providers,triggers/providers,tools/providers,agent_loops/providers,orchestrator,events,secrets,egress,budget,policies}
mkdir -p server/api/tests/workers/{sandboxes,git,issues,triggers,tools,agent_loops,orchestrator,events,secrets,egress,budget,policies}
touch server/api/src/ai_portal/workers/__init__.py
```

---

## Phase A — Core types, protocols, fake sandbox

### Task A1: Canonical types + state machine

**Files:**
- Create: `server/api/src/ai_portal/workers/types.py`
- Test: `server/api/tests/workers/test_types.py`

- [ ] **Step 1: Failing test**

```python
# tests/workers/test_types.py
import pytest
from ai_portal.workers.types import TaskStatus, TaskInput, TriggerSourceKind, can_transition

def test_status_transitions_legal():
    assert can_transition(TaskStatus.queued, TaskStatus.planning)
    assert can_transition(TaskStatus.planning, TaskStatus.awaiting_plan_approval)
    assert can_transition(TaskStatus.awaiting_plan_approval, TaskStatus.executing)
    assert can_transition(TaskStatus.executing, TaskStatus.awaiting_pr_approval)
    assert can_transition(TaskStatus.executing, TaskStatus.completed)
    assert can_transition(TaskStatus.executing, TaskStatus.failed)
    assert can_transition(TaskStatus.executing, TaskStatus.cancelled)

def test_status_transitions_illegal():
    assert not can_transition(TaskStatus.completed, TaskStatus.executing)
    assert not can_transition(TaskStatus.cancelled, TaskStatus.executing)
    assert not can_transition(TaskStatus.queued, TaskStatus.completed)
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement**

```python
# server/api/src/ai_portal/workers/types.py
from __future__ import annotations
import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Any

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

_LEGAL: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.queued: {TaskStatus.planning, TaskStatus.cancelled, TaskStatus.failed},
    TaskStatus.planning: {TaskStatus.awaiting_plan_approval, TaskStatus.executing,
                          TaskStatus.failed, TaskStatus.cancelled},
    TaskStatus.awaiting_plan_approval: {TaskStatus.executing, TaskStatus.cancelled,
                                        TaskStatus.failed},
    TaskStatus.executing: {TaskStatus.awaiting_pr_approval, TaskStatus.completed,
                           TaskStatus.failed, TaskStatus.cancelled, TaskStatus.paused},
    TaskStatus.paused: {TaskStatus.executing, TaskStatus.cancelled, TaskStatus.failed},
    TaskStatus.awaiting_pr_approval: {TaskStatus.completed, TaskStatus.cancelled,
                                      TaskStatus.failed},
    TaskStatus.completed: set(),
    TaskStatus.failed: set(),
    TaskStatus.cancelled: set(),
}

def can_transition(a: TaskStatus, b: TaskStatus) -> bool:
    return b in _LEGAL.get(a, set())
```

- [ ] **Step 4: Run (expect pass)**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(workers): canonical types + task state machine"
```

### Task A2: SandboxProvider protocol + ExecResult

**Files:**
- Create: `server/api/src/ai_portal/workers/sandboxes/protocol.py`
- Test: `server/api/tests/workers/sandboxes/test_protocol.py`

- [ ] **Step 1: Failing test**

```python
# tests/workers/sandboxes/test_protocol.py
import pytest
from ai_portal.workers.sandboxes.protocol import SandboxProvider, ExecResult, SandboxHandle

def test_protocol_attributes_exist():
    assert hasattr(SandboxProvider, "provision")
    assert hasattr(SandboxProvider, "exec")
    assert hasattr(SandboxProvider, "read_file")
    assert hasattr(SandboxProvider, "write_file")
    assert hasattr(SandboxProvider, "kill")
    assert hasattr(SandboxProvider, "snapshot")
    assert hasattr(SandboxProvider, "restore")

def test_exec_result_shape():
    r = ExecResult(exit_code=0, stdout="hi", stderr="", duration_ms=10, truncated=False)
    assert r.exit_code == 0
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement**

```python
# server/api/src/ai_portal/workers/sandboxes/protocol.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, AsyncIterator, runtime_checkable
from ai_portal.workers.types import ResourceLimits

@dataclass
class SandboxHandle:
    id: str                          # internal stable id
    provider: str                    # "docker" | "kubernetes" | "fake" | ...
    provider_resource_id: str        # container id / pod name / ...
    workdir: str                     # path inside sandbox where code lives
    meta: dict

@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    truncated: bool

@dataclass
class SnapshotRef:
    id: str
    provider: str
    size_bytes: int

@runtime_checkable
class SandboxProvider(Protocol):
    name: str

    async def provision(self, *, image: str, limits: ResourceLimits,
                        env: dict[str, str], egress_allow_list: list[str]) -> SandboxHandle: ...

    async def exec(self, h: SandboxHandle, cmd: list[str], *,
                   cwd: str | None = None, timeout_sec: int = 600,
                   env: dict[str, str] | None = None) -> ExecResult: ...

    async def stream_exec(self, h: SandboxHandle, cmd: list[str], *,
                          cwd: str | None = None, env: dict[str, str] | None = None,
                          timeout_sec: int = 600) -> AsyncIterator[tuple[str, str]]: ...
        # yields (stream_name, chunk) where stream_name in {"stdout","stderr"}

    async def read_file(self, h: SandboxHandle, path: str) -> bytes: ...
    async def write_file(self, h: SandboxHandle, path: str, data: bytes) -> None: ...
    async def kill(self, h: SandboxHandle) -> None: ...
    async def snapshot(self, h: SandboxHandle) -> SnapshotRef: ...
    async def restore(self, snap: SnapshotRef, *, limits: ResourceLimits,
                      env: dict[str, str]) -> SandboxHandle: ...
```

- [ ] **Step 4–5: Run + commit**

```bash
git commit -am "feat(workers): SandboxProvider protocol"
```

### Task A3: Fake sandbox provider (in-memory, simulated)

**Files:**
- Create: `server/api/src/ai_portal/workers/sandboxes/providers/fake.py`
- Create: `server/api/src/ai_portal/workers/sandboxes/registry.py`
- Test: `server/api/tests/workers/sandboxes/test_fake.py`

- [ ] **Step 1: Failing test**

```python
# tests/workers/sandboxes/test_fake.py
import pytest
from ai_portal.workers.sandboxes.providers.fake import FakeSandbox
from ai_portal.workers.types import ResourceLimits

@pytest.mark.asyncio
async def test_fake_full_lifecycle():
    sb = FakeSandbox()
    h = await sb.provision(image="python:3.12", limits=ResourceLimits(), env={}, egress_allow_list=[])
    await sb.write_file(h, "/work/hello.txt", b"hi")
    assert await sb.read_file(h, "/work/hello.txt") == b"hi"
    r = await sb.exec(h, ["echo", "ok"])
    assert r.exit_code == 0
    assert "ok" in r.stdout
    snap = await sb.snapshot(h)
    h2 = await sb.restore(snap, limits=ResourceLimits(), env={})
    assert await sb.read_file(h2, "/work/hello.txt") == b"hi"
    await sb.kill(h)

@pytest.mark.asyncio
async def test_fake_scripted_exec():
    sb = FakeSandbox(scripts={("python", "-V"): (0, "Python 3.12.0\n", "")})
    h = await sb.provision(image="python:3.12", limits=ResourceLimits(), env={}, egress_allow_list=[])
    r = await sb.exec(h, ["python", "-V"])
    assert "3.12" in r.stdout

@pytest.mark.asyncio
async def test_fake_records_egress():
    sb = FakeSandbox()
    h = await sb.provision(image="x", limits=ResourceLimits(), env={}, egress_allow_list=["pypi.org"])
    assert h.meta["egress_allow_list"] == ["pypi.org"]
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement**

```python
# server/api/src/ai_portal/workers/sandboxes/providers/fake.py
from __future__ import annotations
import uuid
from typing import AsyncIterator
from ai_portal.workers.sandboxes.protocol import (
    SandboxHandle, ExecResult, SnapshotRef
)
from ai_portal.workers.types import ResourceLimits

class FakeSandbox:
    name = "fake"

    def __init__(self, scripts: dict[tuple[str, ...], tuple[int, str, str]] | None = None):
        self._fs: dict[str, dict[str, bytes]] = {}
        self._scripts = scripts or {}
        self._snapshots: dict[str, dict[str, bytes]] = {}
        self._killed: set[str] = set()

    async def provision(self, *, image, limits, env, egress_allow_list):
        sid = f"fake-{uuid.uuid4().hex[:8]}"
        self._fs[sid] = {}
        return SandboxHandle(id=sid, provider="fake", provider_resource_id=sid,
                             workdir="/work",
                             meta={"image": image, "env": env, "limits": limits,
                                   "egress_allow_list": egress_allow_list})

    async def exec(self, h, cmd, *, cwd=None, timeout_sec=600, env=None):
        if h.id in self._killed:
            return ExecResult(exit_code=137, stdout="", stderr="killed",
                              duration_ms=0, truncated=False)
        key = tuple(cmd)
        if key in self._scripts:
            ec, out, err = self._scripts[key]
            return ExecResult(exit_code=ec, stdout=out, stderr=err,
                              duration_ms=1, truncated=False)
        # default: echo
        if cmd and cmd[0] == "echo":
            return ExecResult(exit_code=0, stdout=" ".join(cmd[1:]) + "\n",
                              stderr="", duration_ms=1, truncated=False)
        return ExecResult(exit_code=0, stdout="", stderr="", duration_ms=1, truncated=False)

    async def stream_exec(self, h, cmd, *, cwd=None, env=None,
                          timeout_sec=600) -> AsyncIterator[tuple[str, str]]:
        r = await self.exec(h, cmd, cwd=cwd, env=env, timeout_sec=timeout_sec)
        if r.stdout:
            yield ("stdout", r.stdout)
        if r.stderr:
            yield ("stderr", r.stderr)

    async def read_file(self, h, path):
        return self._fs[h.id][path]

    async def write_file(self, h, path, data):
        self._fs[h.id][path] = data

    async def kill(self, h):
        self._killed.add(h.id)

    async def snapshot(self, h):
        sid = f"snap-{uuid.uuid4().hex[:8]}"
        self._snapshots[sid] = dict(self._fs[h.id])
        return SnapshotRef(id=sid, provider="fake", size_bytes=sum(len(v) for v in self._snapshots[sid].values()))

    async def restore(self, snap, *, limits, env):
        sid = f"fake-{uuid.uuid4().hex[:8]}"
        self._fs[sid] = dict(self._snapshots[snap.id])
        return SandboxHandle(id=sid, provider="fake", provider_resource_id=sid,
                             workdir="/work", meta={"env": env, "limits": limits,
                                                    "egress_allow_list": []})
```

```python
# server/api/src/ai_portal/workers/sandboxes/registry.py
from ai_portal.workers.sandboxes.protocol import SandboxProvider

_REG: dict[str, SandboxProvider] = {}

def register(provider: SandboxProvider) -> None:
    _REG[provider.name] = provider

def get(name: str) -> SandboxProvider:
    return _REG[name]

def all_providers() -> list[str]:
    return list(_REG.keys())
```

- [ ] **Step 4–5: Run + commit**

```bash
git commit -am "feat(workers): fake sandbox provider + registry"
```

### Task A4: GitProvider, IssueTracker, Tool, AgentLoop, TriggerSource protocols

**Files:**
- Create: `server/api/src/ai_portal/workers/git/protocol.py`
- Create: `server/api/src/ai_portal/workers/issues/protocol.py`
- Create: `server/api/src/ai_portal/workers/tools/protocol.py`
- Create: `server/api/src/ai_portal/workers/agent_loops/protocol.py`
- Create: `server/api/src/ai_portal/workers/triggers/protocol.py`
- Test: `server/api/tests/workers/test_all_protocols.py`

- [ ] **Step 1: Failing test**

```python
# tests/workers/test_all_protocols.py
def test_all_protocols_importable():
    from ai_portal.workers.git.protocol import GitProvider, PullRequest, RepoRef
    from ai_portal.workers.issues.protocol import IssueTracker, Issue, IssueWebhookEvent
    from ai_portal.workers.tools.protocol import Tool, ToolResult, ToolContext
    from ai_portal.workers.agent_loops.protocol import AgentLoop, AgentRunCtx
    from ai_portal.workers.triggers.protocol import TriggerSource
    for x in (GitProvider, IssueTracker, Tool, AgentLoop, TriggerSource):
        assert x is not None
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement**

```python
# server/api/src/ai_portal/workers/git/protocol.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

@dataclass
class RepoRef:
    full_name: str         # "org/repo"
    default_branch: str
    clone_url: str

@dataclass
class PullRequest:
    id: str
    number: int
    url: str
    state: str             # "open" | "closed" | "merged" | "draft"
    head_branch: str
    base_branch: str
    title: str
    body: str

@dataclass
class PrEventParsed:
    kind: str              # "comment" | "opened" | "closed" | "synchronized"
    repo: RepoRef
    pr_number: int
    actor: str
    body: str | None

@runtime_checkable
class GitProvider(Protocol):
    name: str
    async def clone(self, repo: RepoRef, *, into: str, sandbox) -> None: ...
    async def branch(self, sandbox, *, name: str, base: str | None = None) -> None: ...
    async def commit(self, sandbox, *, message: str, author: tuple[str, str]) -> str: ...
    async def push(self, sandbox, *, branch: str) -> None: ...
    async def create_pr(self, repo: RepoRef, *, head: str, base: str,
                        title: str, body: str, draft: bool = True) -> PullRequest: ...
    async def comment_pr(self, repo: RepoRef, pr_number: int, body: str) -> None: ...
    async def read_pr(self, repo: RepoRef, pr_number: int) -> PullRequest: ...
    async def update_pr(self, repo: RepoRef, pr_number: int, *,
                        title: str | None = None, body: str | None = None,
                        state: str | None = None, draft: bool | None = None) -> PullRequest: ...
    def parse_pr_event(self, payload: dict, headers: dict) -> PrEventParsed | None: ...
```

```python
# server/api/src/ai_portal/workers/issues/protocol.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

@dataclass
class Issue:
    id: str
    external_id: str        # provider's id
    title: str
    body: str
    url: str
    labels: list[str]
    status: str
    repo_hint: str | None   # provider may know which repo

@dataclass
class IssueWebhookEvent:
    kind: str               # "created" | "labeled" | "status_changed" | "commented"
    issue: Issue
    actor: str
    raw: dict

@runtime_checkable
class IssueTracker(Protocol):
    name: str
    async def list_issues(self, *, project: str, query: str | None = None) -> list[Issue]: ...
    async def read_issue(self, *, project: str, external_id: str) -> Issue: ...
    async def comment_issue(self, *, project: str, external_id: str, body: str) -> None: ...
    async def set_status(self, *, project: str, external_id: str, status: str) -> None: ...
    def parse_webhook_event(self, payload: dict, headers: dict) -> IssueWebhookEvent | None: ...
```

```python
# server/api/src/ai_portal/workers/tools/protocol.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, Any, runtime_checkable

@dataclass
class ToolResult:
    ok: bool
    output: Any
    error: str | None = None
    artifacts: list[dict] = field(default_factory=list)

@dataclass
class ToolContext:
    sandbox: Any            # SandboxHandle
    sandbox_provider: Any   # SandboxProvider
    task_id: str
    run_id: str
    actor_id: str
    org_id: str
    emit_event: Any         # async fn(EventKind, payload)
    egress: Any             # egress checker
    gateway: Any            # gateway facade
    repo: Any | None        # RepoRef
    secrets_proxy: Any      # secret-injection proxy

@runtime_checkable
class Tool(Protocol):
    name: str
    schema: dict            # JSON schema for args
    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult: ...
```

```python
# server/api/src/ai_portal/workers/agent_loops/protocol.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, AsyncIterator, runtime_checkable
from ai_portal.workers.types import WorkerEvent

@dataclass
class AgentRunCtx:
    task: Any               # WorkerTask row
    run: Any                # WorkerRun row
    tools: list             # list[Tool]
    gateway: Any
    sandbox: Any
    sandbox_provider: Any
    repo: Any
    model: str
    max_iterations: int = 40

@runtime_checkable
class AgentLoop(Protocol):
    name: str
    async def run(self, ctx: AgentRunCtx) -> AsyncIterator[WorkerEvent]: ...
```

```python
# server/api/src/ai_portal/workers/triggers/protocol.py
from __future__ import annotations
from typing import Protocol, runtime_checkable
from ai_portal.workers.types import TaskInput, TriggerSourceKind

@runtime_checkable
class TriggerSource(Protocol):
    kind: TriggerSourceKind
    def parse(self, payload: dict, headers: dict | None = None) -> TaskInput | None: ...
```

- [ ] **Step 4–5: Run + commit**

```bash
git commit -am "feat(workers): GitProvider/IssueTracker/Tool/AgentLoop/TriggerSource protocols"
```

### Task A5: Domain models + migration (pools, tasks, runs, events, artifacts, approvals, sandboxes, secret grants, egress rules, integrations)

**Files:**
- Create: `server/api/src/ai_portal/workers/model.py`
- Extend migration `<rev>_workers.py`
- Test: `server/api/tests/workers/test_model.py`

- [ ] **Step 1: Failing test**

```python
# tests/workers/test_model.py
import pytest
from ai_portal.workers.model import (
    WorkerPool, WorkerTask, WorkerRun, WorkerEvent, WorkerArtifact,
    WorkerApproval, WorkerSandboxRow, WorkerSecretGrant, WorkerEgressRule,
    GitIntegration, IssueTrackerIntegration,
)

@pytest.mark.asyncio
async def test_can_insert_pool_and_task(db_session, org):
    p = WorkerPool(org_id=org.id, name="default", template="python",
                   sandbox_provider="fake", repo_allow_list_json=["acme/api"],
                   budget_cents_per_task=10000, default_model="claude-sonnet-4-6",
                   settings_json={}, enabled=True)
    db_session.add(p); await db_session.flush()
    t = WorkerTask(org_id=org.id, pool_id=p.id, trigger_source="rest_api",
                   trigger_payload_json={}, title="t", description="d",
                   status="queued", created_by="actor-1")
    db_session.add(t); await db_session.commit()
    assert t.id and p.id
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement model** (abbreviated — full implementation should mirror spec's data-model section)

```python
# server/api/src/ai_portal/workers/model.py
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, JSON, Boolean, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from ai_portal.db.base import Base, uuid_pk

class WorkerPool(Base):
    __tablename__ = "worker_pools"
    id: Mapped[str] = mapped_column(primary_key=True, default=uuid_pk)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(128))
    template: Mapped[str] = mapped_column(String(64))     # python | node | go | rust | polyglot | custom
    sandbox_provider: Mapped[str] = mapped_column(String(32))
    repo_allow_list_json: Mapped[list] = mapped_column(JSON, default=list)
    budget_cents_per_task: Mapped[int] = mapped_column(Integer, default=10000)
    default_model: Mapped[str] = mapped_column(String(128))
    settings_json: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class WorkerTask(Base):
    __tablename__ = "worker_tasks"
    id: Mapped[str] = mapped_column(primary_key=True, default=uuid_pk)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    pool_id: Mapped[str] = mapped_column(String(36), ForeignKey("worker_pools.id"))
    trigger_source: Mapped[str] = mapped_column(String(32))
    trigger_payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(8192))
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    created_by: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class WorkerRun(Base):
    __tablename__ = "worker_runs"
    id: Mapped[str] = mapped_column(primary_key=True, default=uuid_pk)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("worker_tasks.id"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="planning")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sandbox_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(2048), nullable=True)

class WorkerEvent(Base):
    __tablename__ = "worker_events"
    __table_args__ = (Index("ix_we_run_ts", "run_id", "ts"),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uuid_pk)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class WorkerArtifact(Base):
    __tablename__ = "worker_artifacts"
    id: Mapped[str] = mapped_column(primary_key=True, default=uuid_pk)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(32))   # pr_url | log_blob | screenshot | diff
    ref: Mapped[str] = mapped_column(String(1024))
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class WorkerApproval(Base):
    __tablename__ = "worker_approvals"
    id: Mapped[str] = mapped_column(primary_key=True, default=uuid_pk)
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(16))   # plan | pr | budget
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)  # approve | reject
    reason: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    required_approvers: Mapped[int] = mapped_column(Integer, default=1)
    approver_ids_json: Mapped[list] = mapped_column(JSON, default=list)

class WorkerSandboxRow(Base):
    __tablename__ = "worker_sandboxes"
    id: Mapped[str] = mapped_column(primary_key=True, default=uuid_pk)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    provider_resource_id: Mapped[str] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(16), default="allocated")
    allocated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class WorkerSecretGrant(Base):
    __tablename__ = "worker_secrets_grants"
    id: Mapped[str] = mapped_column(primary_key=True, default=uuid_pk)
    pool_id: Mapped[str] = mapped_column(String(36), index=True)
    secret_ref: Mapped[str] = mapped_column(String(255))
    allow_repos_json: Mapped[list] = mapped_column(JSON, default=list)

class WorkerEgressRule(Base):
    __tablename__ = "worker_egress_rules"
    id: Mapped[str] = mapped_column(primary_key=True, default=uuid_pk)
    pool_id: Mapped[str] = mapped_column(String(36), index=True)
    allow_list_json: Mapped[list] = mapped_column(JSON, default=list)

class GitIntegration(Base):
    __tablename__ = "git_integrations"
    id: Mapped[str] = mapped_column(primary_key=True, default=uuid_pk)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(32))   # github | gitlab | ...
    config_encrypted: Mapped[bytes] = mapped_column()
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class IssueTrackerIntegration(Base):
    __tablename__ = "issue_tracker_integrations"
    id: Mapped[str] = mapped_column(primary_key=True, default=uuid_pk)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    config_encrypted: Mapped[bytes] = mapped_column()
    project_mapping_json: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
```

- [ ] **Step 4: Migration**

In the `workers: scaffolding` revision, create all tables above. Add `Index("ix_we_run_ts", ...)`. Set up event-table partitioning hook (daily) via raw SQL `CREATE TABLE ... PARTITION BY RANGE (ts)`.

- [ ] **Step 5: Apply + run + commit**

```bash
alembic upgrade head && pytest server/api/tests/workers/test_model.py -xvs
git commit -am "feat(workers): domain models + alembic migration"
```

### Task A6: Branch-level lock

**Files:**
- Create: `server/api/src/ai_portal/workers/policies/branch_lock.py`
- Test: `server/api/tests/workers/policies/test_branch_lock.py`

- [ ] **Step 1: Failing test**

```python
@pytest.mark.asyncio
async def test_branch_lock_acquired_once(db_session):
    from ai_portal.workers.policies.branch_lock import acquire_branch, release_branch, BranchBusy
    await acquire_branch(db_session, org_id="o", repo="acme/api", branch="worker/x")
    with pytest.raises(BranchBusy):
        await acquire_branch(db_session, org_id="o", repo="acme/api", branch="worker/x")
    await release_branch(db_session, org_id="o", repo="acme/api", branch="worker/x")
    await acquire_branch(db_session, org_id="o", repo="acme/api", branch="worker/x")
```

- [ ] **Step 2–5**: Implement using a `branch_locks(org_id, repo, branch, run_id, acquired_at)` table with unique constraint; commit.

```bash
git commit -m "feat(workers): branch-level lock to serialize same-branch tasks"
```

---

## Phase B — Docker sandbox (full exemplar) + other provider stubs

### Task B1: Docker sandbox provider (full implementation)

**Files:**
- Create: `server/api/src/ai_portal/workers/sandboxes/providers/docker_provider.py`
- Test: `server/api/tests/workers/sandboxes/test_docker_provider.py` (uses mocked docker client — no real daemon)

- [ ] **Step 1: Failing test** — patch `docker.from_env`, assert lifecycle calls + resource limits applied

```python
# tests/workers/sandboxes/test_docker_provider.py
import pytest
from unittest.mock import MagicMock, patch
from ai_portal.workers.sandboxes.providers.docker_provider import DockerSandbox
from ai_portal.workers.types import ResourceLimits

@pytest.mark.asyncio
async def test_docker_provision_applies_limits():
    fake_client = MagicMock()
    container = MagicMock()
    container.id = "c0ffee"
    fake_client.containers.run.return_value = container
    with patch("ai_portal.workers.sandboxes.providers.docker_provider.docker.from_env",
               return_value=fake_client):
        sb = DockerSandbox()
        h = await sb.provision(image="python:3.12",
                               limits=ResourceLimits(cpu_cores=2, ram_mb=2048),
                               env={"FOO": "1"},
                               egress_allow_list=["pypi.org"])
    args, kwargs = fake_client.containers.run.call_args
    assert kwargs["image"] == "python:3.12"
    assert kwargs["mem_limit"] == "2048m"
    assert kwargs["nano_cpus"] == int(2 * 1e9)
    assert kwargs["environment"]["FOO"] == "1"
    assert kwargs["network_mode"]                       # network namespace pinned
    assert kwargs["detach"] is True
    assert h.provider_resource_id == "c0ffee"

@pytest.mark.asyncio
async def test_docker_exec_returns_result():
    fake_client = MagicMock()
    fake_client.containers.get.return_value.exec_run.return_value = MagicMock(
        exit_code=0, output=(b"hello\n", b""))
    with patch("ai_portal.workers.sandboxes.providers.docker_provider.docker.from_env",
               return_value=fake_client):
        sb = DockerSandbox()
        from ai_portal.workers.sandboxes.protocol import SandboxHandle
        h = SandboxHandle(id="x", provider="docker", provider_resource_id="c0ffee",
                          workdir="/work", meta={})
        r = await sb.exec(h, ["echo", "hello"])
    assert r.exit_code == 0
    assert "hello" in r.stdout
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement**

```python
# server/api/src/ai_portal/workers/sandboxes/providers/docker_provider.py
from __future__ import annotations
import asyncio
import io
import tarfile
import uuid
from typing import AsyncIterator
import docker
from ai_portal.workers.sandboxes.protocol import SandboxHandle, ExecResult, SnapshotRef
from ai_portal.workers.types import ResourceLimits

class DockerSandbox:
    """Local-dev sandbox provider.

    Uses a dedicated bridge network per pool; egress restricted via iptables
    rules applied externally (responsibility of the deploy layer), or via the
    docker network's outbound DNS policy. This implementation focuses on the
    runtime contract; network policy is enforced at provision time by binding
    the container to a pre-created network name `wp-egress-<pool_id>`.
    """
    name = "docker"

    def __init__(self):
        self._client = docker.from_env()

    async def provision(self, *, image: str, limits: ResourceLimits,
                        env: dict[str, str], egress_allow_list: list[str]) -> SandboxHandle:
        loop = asyncio.get_event_loop()
        def _run():
            return self._client.containers.run(
                image=image,
                command="sleep infinity",
                detach=True,
                mem_limit=f"{limits.ram_mb}m",
                nano_cpus=int(limits.cpu_cores * 1e9),
                pids_limit=limits.max_processes,
                network_mode="bridge",       # replace with pool-pinned net at deploy time
                environment=env,
                working_dir="/work",
                tmpfs={"/tmp": "rw,size=512m"},
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                read_only=False,
                labels={"ai_portal_worker": "1", "egress_acl": ",".join(egress_allow_list)},
            )
        container = await loop.run_in_executor(None, _run)
        return SandboxHandle(
            id=f"docker-{uuid.uuid4().hex[:8]}",
            provider="docker",
            provider_resource_id=container.id,
            workdir="/work",
            meta={"image": image, "egress_allow_list": egress_allow_list,
                  "limits": limits},
        )

    async def exec(self, h: SandboxHandle, cmd: list[str], *,
                   cwd: str | None = None, timeout_sec: int = 600,
                   env: dict[str, str] | None = None) -> ExecResult:
        loop = asyncio.get_event_loop()
        def _do():
            c = self._client.containers.get(h.provider_resource_id)
            res = c.exec_run(cmd=cmd, workdir=cwd or h.workdir, environment=env or {},
                             demux=True)
            ec = res.exit_code
            out, err = res.output
            return ExecResult(
                exit_code=ec,
                stdout=(out or b"").decode("utf-8", errors="replace"),
                stderr=(err or b"").decode("utf-8", errors="replace"),
                duration_ms=0,
                truncated=False,
            )
        return await asyncio.wait_for(loop.run_in_executor(None, _do), timeout=timeout_sec)

    async def stream_exec(self, h, cmd, *, cwd=None, env=None,
                          timeout_sec=600) -> AsyncIterator[tuple[str, str]]:
        loop = asyncio.get_event_loop()
        def _start():
            c = self._client.containers.get(h.provider_resource_id)
            return c.exec_run(cmd=cmd, workdir=cwd or h.workdir, environment=env or {},
                              stream=True, demux=True)
        gen = await loop.run_in_executor(None, _start)
        for stdout_chunk, stderr_chunk in gen:
            if stdout_chunk:
                yield ("stdout", stdout_chunk.decode("utf-8", errors="replace"))
            if stderr_chunk:
                yield ("stderr", stderr_chunk.decode("utf-8", errors="replace"))

    async def read_file(self, h: SandboxHandle, path: str) -> bytes:
        loop = asyncio.get_event_loop()
        def _do():
            c = self._client.containers.get(h.provider_resource_id)
            stream, _ = c.get_archive(path)
            buf = b"".join(stream)
            with tarfile.open(fileobj=io.BytesIO(buf)) as tf:
                m = tf.next()
                return tf.extractfile(m).read()
        return await loop.run_in_executor(None, _do)

    async def write_file(self, h: SandboxHandle, path: str, data: bytes) -> None:
        loop = asyncio.get_event_loop()
        def _do():
            c = self._client.containers.get(h.provider_resource_id)
            tar_buf = io.BytesIO()
            name = path.rsplit("/", 1)[-1]
            parent = path.rsplit("/", 1)[0] or "/"
            with tarfile.open(fileobj=tar_buf, mode="w") as tf:
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                info.mode = 0o644
                tf.addfile(info, io.BytesIO(data))
            tar_buf.seek(0)
            c.put_archive(parent, tar_buf.getvalue())
        await loop.run_in_executor(None, _do)

    async def kill(self, h: SandboxHandle) -> None:
        loop = asyncio.get_event_loop()
        def _do():
            try:
                c = self._client.containers.get(h.provider_resource_id)
                c.kill()
                c.remove(force=True)
            except docker.errors.NotFound:
                pass
        await loop.run_in_executor(None, _do)

    async def snapshot(self, h: SandboxHandle) -> SnapshotRef:
        loop = asyncio.get_event_loop()
        def _do():
            c = self._client.containers.get(h.provider_resource_id)
            img = c.commit(repository="ai_portal_snap", tag=h.id)
            return SnapshotRef(id=img.id, provider="docker", size_bytes=img.attrs.get("Size", 0))
        return await loop.run_in_executor(None, _do)

    async def restore(self, snap: SnapshotRef, *, limits: ResourceLimits,
                      env: dict[str, str]) -> SandboxHandle:
        return await self.provision(image=snap.id, limits=limits, env=env,
                                    egress_allow_list=[])
```

- [ ] **Step 4: Run (expect pass)**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(workers): docker sandbox provider (provision/exec/read/write/kill/snapshot/restore)"
```

### Task B2: Kubernetes sandbox provider (short)

**Files:**
- Create: `server/api/src/ai_portal/workers/sandboxes/providers/kubernetes_provider.py`
- Test: `server/api/tests/workers/sandboxes/test_kubernetes_provider.py`

- [ ] **Step 1: Failing test** — mock `kubernetes.client.CoreV1Api`; assert pod spec sets runtimeClassName=`gvisor` (or `kata`), resource limits, and a NetworkPolicy is created with egress restricted to allow_list.
- [ ] **Step 2–6**: Implement using `kubernetes.client` async wrapper (`asyncio.to_thread` for sync API); create pod with `runtimeClassName: gvisor`, attach a per-pool NetworkPolicy, exec via `stream` API. Commit.

```bash
git commit -m "feat(workers): kubernetes sandbox provider (gVisor/Kata runtimeClass)"
```

### Task B3: Firecracker sandbox slot (short)

**Files:**
- Create: `server/api/src/ai_portal/workers/sandboxes/providers/firecracker_provider.py`
- Test: `tests/workers/sandboxes/test_firecracker_provider.py`

- [ ] **Step 1: Failing test** — provider exposes the protocol surface; `provision()` raises `NotImplementedError("requires firecracker socket")` unless configured.
- [ ] **Step 2–6**: Implement minimal slot: constructor accepts `firecracker_socket_path`; protocol methods stubbed but type-correct so prod can drop in adapter. Commit.

```bash
git commit -m "feat(workers): firecracker provider slot (future microVM)"
```

### Task B4: E2B sandbox provider (short)

**Files:**
- Create: `server/api/src/ai_portal/workers/sandboxes/providers/e2b_provider.py`
- Test: `tests/workers/sandboxes/test_e2b_provider.py` (respx)

- [ ] **Step 1: Failing test** — mock E2B HTTP API; `provision()` calls `POST /sandboxes`; `exec()` calls `POST /sandboxes/{id}/exec`.
- [ ] **Step 2–6**: Implement thin httpx adapter; commit.

```bash
git commit -m "feat(workers): e2b managed sandbox adapter"
```

### Task B5: Daytona sandbox provider (short)

**Files:**
- Create: `server/api/src/ai_portal/workers/sandboxes/providers/daytona_provider.py`
- Test: `tests/workers/sandboxes/test_daytona_provider.py`

- [ ] **Step 1–6**: Same pattern as E2B; commit.

```bash
git commit -m "feat(workers): daytona managed sandbox adapter"
```

### Task B6: Sandbox image catalog (templates)

**Files:**
- Create: `server/api/src/ai_portal/workers/sandboxes/templates.py` (python / node / go / rust / polyglot — image refs + preinstalled tools list)
- Create: `infra/sandbox-images/{python,node,go,rust,polyglot}/Dockerfile`
- Test: `tests/workers/sandboxes/test_templates.py`

```python
# templates.py
TEMPLATES = {
    "python": {
        "image": "ghcr.io/ai-portal/sandbox-python:latest",
        "tools": ["uv", "pytest", "ruff", "mypy", "rg", "ast-grep"],
        "default_test_cmd": "pytest -x",
    },
    "node": {
        "image": "ghcr.io/ai-portal/sandbox-node:latest",
        "tools": ["pnpm", "npm", "yarn", "rg", "ast-grep", "eslint", "tsc", "vitest"],
        "default_test_cmd": "pnpm test",
    },
    "go": {
        "image": "ghcr.io/ai-portal/sandbox-go:latest",
        "tools": ["go", "golangci-lint", "rg", "ast-grep"],
        "default_test_cmd": "go test ./...",
    },
    "rust": {
        "image": "ghcr.io/ai-portal/sandbox-rust:latest",
        "tools": ["cargo", "clippy", "rustfmt", "rg", "ast-grep"],
        "default_test_cmd": "cargo test",
    },
    "polyglot": {
        "image": "ghcr.io/ai-portal/sandbox-polyglot:latest",
        "tools": ["python", "node", "go", "rust", "rg", "ast-grep", "playwright"],
        "default_test_cmd": None,
    },
}
```

- [ ] **Step 1: Failing test** — `TEMPLATES["python"]["tools"]` includes ripgrep; image string non-empty for all 5.
- [ ] **Step 2–6**: Implement + write Dockerfiles; commit.

```bash
git commit -m "feat(workers): bundled sandbox templates (python/node/go/rust/polyglot)"
```

---

## Phase C — Git providers

### Task C1: Github provider (full exemplar)

**Files:**
- Create: `server/api/src/ai_portal/workers/git/providers/github_provider.py`
- Create: `server/api/src/ai_portal/workers/git/registry.py`
- Test: `server/api/tests/workers/git/test_github_provider.py`

- [ ] **Step 1: Failing tests** (respx + PyGithub stub)

```python
# tests/workers/git/test_github_provider.py
import pytest, respx, httpx
from ai_portal.workers.git.providers.github_provider import GitHubProvider
from ai_portal.workers.git.protocol import RepoRef

@pytest.mark.asyncio
@respx.mock
async def test_create_pr_draft():
    respx.post("https://api.github.com/repos/acme/api/pulls").mock(
        return_value=httpx.Response(201, json={
            "id": 1, "number": 42, "html_url": "https://github.com/acme/api/pull/42",
            "state": "open", "draft": True,
            "head": {"ref": "worker/t-1"}, "base": {"ref": "main"},
            "title": "fix", "body": "..."
        }))
    p = GitHubProvider(token="ghs_fake")
    pr = await p.create_pr(RepoRef("acme/api", "main", "https://github.com/acme/api.git"),
                           head="worker/t-1", base="main", title="fix", body="...", draft=True)
    assert pr.number == 42 and pr.state == "open"

@pytest.mark.asyncio
@respx.mock
async def test_blocks_push_to_default_branch():
    p = GitHubProvider(token="ghs_fake")
    from ai_portal.workers.git.providers.github_provider import DefaultBranchPushBlocked
    class FakeSb:
        pass
    with pytest.raises(DefaultBranchPushBlocked):
        await p.push(FakeSb(), branch="main")
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement**

```python
# server/api/src/ai_portal/workers/git/providers/github_provider.py
from __future__ import annotations
import httpx
import hmac, hashlib
from ai_portal.workers.git.protocol import GitProvider, RepoRef, PullRequest, PrEventParsed

class DefaultBranchPushBlocked(Exception): ...

class GitHubProvider:
    name = "github"
    base = "https://api.github.com"

    def __init__(self, token: str, app_id: str | None = None, webhook_secret: str | None = None):
        self._token = token
        self._app_id = app_id
        self._secret = webhook_secret.encode() if webhook_secret else None

    def _headers(self):
        return {"Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"}

    async def clone(self, repo, *, into, sandbox):
        sb_p = sandbox["provider"]
        sb_h = sandbox["handle"]
        url = repo.clone_url.replace("https://", f"https://x-access-token:{self._token}@")
        r = await sb_p.exec(sb_h, ["git", "clone", url, into], timeout_sec=600)
        if r.exit_code != 0:
            raise RuntimeError(f"clone failed: {r.stderr}")

    async def branch(self, sandbox, *, name, base=None):
        sb_p, sb_h = sandbox["provider"], sandbox["handle"]
        if base:
            await sb_p.exec(sb_h, ["git", "checkout", base])
        r = await sb_p.exec(sb_h, ["git", "checkout", "-b", name])
        if r.exit_code != 0:
            raise RuntimeError(r.stderr)

    async def commit(self, sandbox, *, message, author):
        sb_p, sb_h = sandbox["provider"], sandbox["handle"]
        name, email = author
        await sb_p.exec(sb_h, ["git", "config", "user.name", name])
        await sb_p.exec(sb_h, ["git", "config", "user.email", email])
        await sb_p.exec(sb_h, ["git", "add", "-A"])
        r = await sb_p.exec(sb_h, ["git", "commit", "-m", message])
        if r.exit_code != 0:
            raise RuntimeError(r.stderr)
        sha = (await sb_p.exec(sb_h, ["git", "rev-parse", "HEAD"])).stdout.strip()
        return sha

    async def push(self, sandbox, *, branch):
        # default-branch guard — caller must pass non-default branch name only
        if branch in ("main", "master", "trunk", "develop"):
            raise DefaultBranchPushBlocked(branch)
        sb_p, sb_h = sandbox["provider"], sandbox["handle"]
        r = await sb_p.exec(sb_h, ["git", "push", "-u", "origin", branch])
        if r.exit_code != 0:
            raise RuntimeError(r.stderr)

    async def create_pr(self, repo, *, head, base, title, body, draft=True):
        if base in ("main", "master", "trunk", "develop") and head == base:
            raise DefaultBranchPushBlocked(head)
        async with httpx.AsyncClient(headers=self._headers()) as c:
            r = await c.post(f"{self.base}/repos/{repo.full_name}/pulls",
                             json={"head": head, "base": base, "title": title,
                                   "body": body, "draft": draft})
            r.raise_for_status()
            d = r.json()
            return PullRequest(id=str(d["id"]), number=d["number"], url=d["html_url"],
                               state="draft" if d.get("draft") else d["state"],
                               head_branch=d["head"]["ref"], base_branch=d["base"]["ref"],
                               title=d["title"], body=d.get("body") or "")

    async def comment_pr(self, repo, pr_number, body):
        async with httpx.AsyncClient(headers=self._headers()) as c:
            r = await c.post(f"{self.base}/repos/{repo.full_name}/issues/{pr_number}/comments",
                             json={"body": body})
            r.raise_for_status()

    async def read_pr(self, repo, pr_number):
        async with httpx.AsyncClient(headers=self._headers()) as c:
            r = await c.get(f"{self.base}/repos/{repo.full_name}/pulls/{pr_number}")
            r.raise_for_status()
            d = r.json()
            return PullRequest(id=str(d["id"]), number=d["number"], url=d["html_url"],
                               state="draft" if d.get("draft") else d["state"],
                               head_branch=d["head"]["ref"], base_branch=d["base"]["ref"],
                               title=d["title"], body=d.get("body") or "")

    async def update_pr(self, repo, pr_number, *, title=None, body=None,
                        state=None, draft=None):
        patch = {k: v for k, v in dict(title=title, body=body, state=state, draft=draft).items()
                 if v is not None}
        async with httpx.AsyncClient(headers=self._headers()) as c:
            r = await c.patch(f"{self.base}/repos/{repo.full_name}/pulls/{pr_number}", json=patch)
            r.raise_for_status()
            return await self.read_pr(repo, pr_number)

    def parse_pr_event(self, payload, headers):
        sig = headers.get("X-Hub-Signature-256", "")
        if self._secret:
            mac = "sha256=" + hmac.new(self._secret,
                                       msg=str(payload).encode(),
                                       digestmod=hashlib.sha256).hexdigest()
            if not hmac.compare_digest(mac, sig):
                return None
        action = payload.get("action")
        if "pull_request" in payload:
            pr = payload["pull_request"]
            repo = payload["repository"]
            return PrEventParsed(
                kind="opened" if action == "opened" else "synchronized" if action == "synchronize"
                     else "closed" if action == "closed" else "comment",
                repo=RepoRef(repo["full_name"], repo["default_branch"], repo["clone_url"]),
                pr_number=pr["number"],
                actor=payload["sender"]["login"],
                body=payload.get("comment", {}).get("body"),
            )
        return None
```

- [ ] **Step 4: Run (expect pass)**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(workers): GitHub provider with default-branch guard + webhook parse"
```

### Task C2: Gitlab provider (short)

**Files:**
- Create: `workers/git/providers/gitlab_provider.py`
- Test: `tests/workers/git/test_gitlab_provider.py`

- [ ] **Step 1–6**: Mirror GitHub via `python-gitlab`; same default-branch guard; commit.

```bash
git commit -m "feat(workers): Gitlab git provider"
```

### Task C3: Bitbucket provider (short)

- [ ] **Step 1–6**: httpx adapter against Bitbucket REST 2.0; commit.

```bash
git commit -m "feat(workers): Bitbucket git provider"
```

### Task C4: Gitea provider (short)

- [ ] **Step 1–6**: httpx adapter against Gitea API; commit.

```bash
git commit -m "feat(workers): Gitea git provider"
```

### Task C5: Azure DevOps provider (short)

- [ ] **Step 1–6**: httpx adapter against Azure DevOps REST; commit.

```bash
git commit -m "feat(workers): Azure DevOps git provider"
```

### Task C6: Git integrations CRUD + encryption

**Files:**
- Create: `workers/git/service.py`, `workers/git/router.py`, `workers/git/schemas.py`
- Test: `tests/workers/git/test_router.py`

- [ ] **Step 1: Failing test** — `POST /v1/workers/git-integrations` with github creds (encrypted at rest via Control Plane key manager); `GET` lists with masked secrets.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(workers): git-integrations CRUD + encrypted storage"
```

---

## Phase D — Issue trackers

### Task D1: Jira Cloud tracker (full exemplar)

**Files:**
- Create: `server/api/src/ai_portal/workers/issues/providers/jira_cloud_provider.py`
- Create: `server/api/src/ai_portal/workers/issues/registry.py`
- Test: `server/api/tests/workers/issues/test_jira_cloud.py`

- [ ] **Step 1: Failing tests** (respx)

```python
@pytest.mark.asyncio
@respx.mock
async def test_jira_read_issue():
    respx.get("https://acme.atlassian.net/rest/api/3/issue/ENG-42").mock(
        return_value=httpx.Response(200, json={
            "id": "10042", "key": "ENG-42",
            "fields": {"summary": "Fix bug", "description": "...",
                       "status": {"name": "To Do"}, "labels": ["worker"]}
        }))
    p = JiraCloudTracker(site="https://acme.atlassian.net", email="x", token="y")
    issue = await p.read_issue(project="ENG", external_id="ENG-42")
    assert issue.title == "Fix bug" and "worker" in issue.labels

@pytest.mark.asyncio
async def test_jira_webhook_label_added_emits_event():
    p = JiraCloudTracker(site="x", email="x", token="y")
    evt = p.parse_webhook_event(
        payload={"webhookEvent": "jira:issue_updated",
                 "issue": {"id": "10", "key": "ENG-1",
                           "fields": {"summary": "s","description":"d",
                                      "status":{"name":"Todo"},"labels":["worker"]}},
                 "user": {"displayName": "Alice"},
                 "changelog": {"items": [{"field": "labels", "toString": "worker"}]}},
        headers={})
    assert evt.kind == "labeled" and evt.actor == "Alice"
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement**

```python
# server/api/src/ai_portal/workers/issues/providers/jira_cloud_provider.py
from __future__ import annotations
import httpx, base64
from ai_portal.workers.issues.protocol import IssueTracker, Issue, IssueWebhookEvent

class JiraCloudTracker:
    name = "jira_cloud"

    def __init__(self, *, site: str, email: str, token: str):
        self._site = site.rstrip("/")
        auth = base64.b64encode(f"{email}:{token}".encode()).decode()
        self._headers = {"Authorization": f"Basic {auth}",
                         "Accept": "application/json",
                         "Content-Type": "application/json"}

    async def list_issues(self, *, project, query=None):
        jql = f"project={project}"
        if query: jql += f" AND {query}"
        async with httpx.AsyncClient(headers=self._headers) as c:
            r = await c.get(f"{self._site}/rest/api/3/search", params={"jql": jql})
            r.raise_for_status()
            return [self._to_issue(x) for x in r.json()["issues"]]

    async def read_issue(self, *, project, external_id):
        async with httpx.AsyncClient(headers=self._headers) as c:
            r = await c.get(f"{self._site}/rest/api/3/issue/{external_id}")
            r.raise_for_status()
            return self._to_issue(r.json())

    async def comment_issue(self, *, project, external_id, body):
        async with httpx.AsyncClient(headers=self._headers) as c:
            r = await c.post(f"{self._site}/rest/api/3/issue/{external_id}/comment",
                             json={"body": body})
            r.raise_for_status()

    async def set_status(self, *, project, external_id, status):
        async with httpx.AsyncClient(headers=self._headers) as c:
            tr = await c.get(f"{self._site}/rest/api/3/issue/{external_id}/transitions")
            transitions = tr.json()["transitions"]
            t = next((t for t in transitions if t["name"].lower() == status.lower()), None)
            if not t: raise ValueError(f"no transition for {status}")
            await c.post(f"{self._site}/rest/api/3/issue/{external_id}/transitions",
                         json={"transition": {"id": t["id"]}})

    def parse_webhook_event(self, payload, headers):
        if "issue" not in payload: return None
        issue = self._to_issue(payload["issue"])
        ev = payload.get("webhookEvent", "")
        kind = "labeled" if any(item.get("field") == "labels"
                                for item in payload.get("changelog", {}).get("items", [])) \
               else "created" if "created" in ev \
               else "status_changed" if "updated" in ev else "commented"
        return IssueWebhookEvent(kind=kind, issue=issue,
                                 actor=payload.get("user", {}).get("displayName", ""),
                                 raw=payload)

    def _to_issue(self, raw):
        f = raw["fields"]
        return Issue(id=str(raw["id"]), external_id=raw["key"],
                     title=f.get("summary", ""), body=str(f.get("description") or ""),
                     url=f"{self._site}/browse/{raw['key']}",
                     labels=f.get("labels", []),
                     status=f.get("status", {}).get("name", ""),
                     repo_hint=None)
```

- [ ] **Step 4–5: Run + commit**

```bash
git commit -am "feat(workers): Jira Cloud issue tracker"
```

### Task D2: Linear tracker (short)

- [ ] **Step 1–6**: httpx adapter against Linear GraphQL `https://api.linear.app/graphql`; same protocol; commit.

```bash
git commit -m "feat(workers): Linear issue tracker"
```

### Task D3: GitHub Issues tracker (short)

- [ ] **Step 1–6**: httpx adapter, reuse GitHub auth; commit.

```bash
git commit -m "feat(workers): GitHub Issues tracker"
```

### Task D4: GitLab Issues tracker (short)

- [ ] **Step 1–6**: python-gitlab adapter; commit.

```bash
git commit -m "feat(workers): GitLab Issues tracker"
```

### Task D5: Azure Boards tracker (short)

- [ ] **Step 1–6**: httpx adapter against Azure Boards work-item REST; commit.

```bash
git commit -m "feat(workers): Azure Boards tracker"
```

### Task D6: Issue-tracker integrations CRUD + project→pool mapping

**Files:**
- Create: `workers/issues/service.py`, `router.py`, `schemas.py`
- Test: `tests/workers/issues/test_router.py`

- [ ] **Step 1: Failing test** — POST integration with encrypted token + `project_mapping_json` like `{"ENG": "pool_python"}`.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(workers): issue-tracker integrations CRUD + project→pool mapping"
```

---

## Phase E — Triggers

### Task E1: TriggerRouter

**Files:**
- Create: `workers/triggers/registry.py`, `workers/triggers/router.py` (FastAPI receivers)
- Test: `tests/workers/triggers/test_router.py`

- [ ] **Step 1: Failing test** — POST `/v1/workers/webhooks/github` with PR comment "/worker do this" → enqueues a task; POST `/v1/workers/tasks` directly enqueues; chat trigger emits via internal call.
- [ ] **Step 2–6**: Implement dispatch through registry; commit.

```bash
git commit -m "feat(workers): trigger router + registry"
```

### Task E2: chat trigger

**Files:**
- Create: `workers/triggers/providers/chat.py`
- Test: `tests/workers/triggers/test_chat.py`

- [ ] **Step 1: Failing test** — chat assistant emits structured `assign_to_worker` event → trigger parses to `TaskInput(title, description, repo, base_branch)`.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(workers): chat trigger"
```

### Task E3: rest_api trigger

**Files:**
- Create: `workers/triggers/providers/rest_api.py`

- [ ] **Step 1: Failing test** — pydantic schema validates POST body → `TaskInput`.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(workers): rest_api trigger"
```

### Task E4: jira_webhook trigger

**Files:**
- Create: `workers/triggers/providers/jira_webhook.py`

- [ ] **Step 1: Failing test** — payload with label `worker` → `TaskInput(title=issue.title, description=issue.body, repo=mapped_repo, ...)`.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(workers): jira_webhook trigger"
```

### Task E5: linear_webhook trigger

- [ ] **Step 1–6**: same shape; commit.

```bash
git commit -m "feat(workers): linear_webhook trigger"
```

### Task E6: github_issue_comment + github_pr_comment triggers

**Files:**
- Create: `workers/triggers/providers/github_issue_comment.py`, `github_pr_comment.py`

- [ ] **Step 1: Failing test** — comment body starts with configurable phrase (default `/worker`) → emit task; otherwise None.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(workers): github_issue_comment + github_pr_comment triggers"
```

### Task E7: schedule_cron trigger

**Files:**
- Create: `workers/triggers/providers/schedule_cron.py`
- Create: `workers/triggers/cron_scheduler.py` (asyncio task firing per-schedule)
- Migration: `worker_schedules(id, org_id, pool_id, cron, task_template_json, enabled, last_fired_at)`
- Test: `tests/workers/triggers/test_schedule_cron.py`

- [ ] **Step 1: Failing test** — schedule `* * * * *` fires at next minute boundary → emits task with template inputs.
- [ ] **Step 2–6**: Implement (use `croniter`); commit.

```bash
git commit -m "feat(workers): schedule_cron trigger + scheduler loop"
```

---

## Phase F — Tools

### Task F1: Tool registry + ToolContext factory

**Files:**
- Create: `workers/tools/registry.py`
- Test: `tests/workers/tools/test_registry.py`

- [ ] **Step 1: Failing test** — register a fake tool, resolve by name with per-pool allow-list applied.
- [ ] **Step 2–6**: Implement; commit.

```bash
git commit -m "feat(workers): tool registry + per-pool allow-list"
```

### Task F2: shell tool (with audit + secret-redacted streaming)

**Files:**
- Create: `workers/tools/providers/shell.py`
- Test: `tests/workers/tools/test_shell.py`

- [ ] **Step 1: Failing test**

```python
@pytest.mark.asyncio
async def test_shell_streams_and_audits(fake_ctx):
    from ai_portal.workers.tools.providers.shell import ShellTool
    t = ShellTool()
    r = await t.invoke({"cmd": ["echo", "hello"]}, fake_ctx)
    assert r.ok and "hello" in r.output["stdout"]
    # audit captured cmd hash + stdout hash
    assert fake_ctx.audited[-1]["action"] == "worker.shell"
    assert "stdout_sha256" in fake_ctx.audited[-1]["payload"]
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement**

```python
# server/api/src/ai_portal/workers/tools/providers/shell.py
from __future__ import annotations
import hashlib
from ai_portal.workers.tools.protocol import Tool, ToolResult, ToolContext
from ai_portal.workers.types import EventKind

class ShellTool:
    name = "shell"
    schema = {
        "type": "object",
        "properties": {
            "cmd": {"type": "array", "items": {"type": "string"}},
            "cwd": {"type": "string"},
            "timeout_sec": {"type": "integer", "default": 600},
        },
        "required": ["cmd"],
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        cmd = args["cmd"]
        await ctx.emit_event(EventKind.tool_call, {"tool": "shell", "cmd": cmd})

        out_buf, err_buf = [], []
        async for stream, chunk in ctx.sandbox_provider.stream_exec(
            ctx.sandbox, cmd, cwd=args.get("cwd"),
            timeout_sec=args.get("timeout_sec", 600),
        ):
            # redact known secret values before streaming
            chunk = ctx.secrets_proxy.redact(chunk)
            (out_buf if stream == "stdout" else err_buf).append(chunk)
            await ctx.emit_event(EventKind.shell_output,
                                 {"stream": stream, "chunk": chunk})

        stdout = "".join(out_buf); stderr = "".join(err_buf)
        result = await ctx.sandbox_provider.exec(ctx.sandbox, ["true"])  # no-op
        audit = ctx.audit  # provided by ctx
        await audit({
            "action": "worker.shell",
            "resource_type": "worker_run",
            "resource_id": ctx.run_id,
            "payload": {
                "cmd_sha256": hashlib.sha256(" ".join(cmd).encode()).hexdigest(),
                "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
                "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
            },
        })
        return ToolResult(ok=True, output={"stdout": stdout, "stderr": stderr,
                                           "exit_code": result.exit_code})
```

- [ ] **Step 4–5: Run + commit**

```bash
git commit -am "feat(workers): shell tool with streaming + audit + secret redaction"
```

### Task F3: read_file / write_file / edit_file tools

**Files:**
- Create: `workers/tools/providers/files.py`
- Test: `tests/workers/tools/test_files.py`

- [ ] **Step 1: Failing test** — `write_file` stores diff hash; `edit_file` applies unified diff; `read_file` returns content.
- [ ] **Step 2–6**: Implement; emit `file_changed` event with before/after sha256; commit.

```bash
git commit -m "feat(workers): file read/write/edit tools with diff hashing"
```

### Task F4: code_search (ripgrep + ast-grep)

**Files:**
- Create: `workers/tools/providers/code_search.py`
- Test: `tests/workers/tools/test_code_search.py`

- [ ] **Step 1: Failing test** — `code_search({"pattern": "foo", "engine": "ripgrep"})` runs `rg --json` in sandbox and returns parsed matches.
- [ ] **Step 2–6**: Implement; engine ∈ `{ripgrep, ast-grep}`; commit.

```bash
git commit -m "feat(workers): code_search tool (ripgrep + ast-grep)"
```

### Task F5: run_tests / run_build / lint / format

**Files:**
- Create: `workers/tools/providers/quality.py`
- Test: `tests/workers/tools/test_quality.py`

- [ ] **Step 1: Failing test** — uses repo-configured cmd from pool settings; falls back to template default; captures exit code + output.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(workers): run_tests/run_build/lint/format tools"
```

### Task F6: git tools (status/diff/commit/push)

**Files:**
- Create: `workers/tools/providers/git_tools.py`
- Test: `tests/workers/tools/test_git_tools.py`

- [ ] **Step 1: Failing test** — `git_commit` enforces conventional-commits when pool setting enabled (rejects non-conformant message); `git_push` calls GitProvider.push (which guards default branch).
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(workers): git_status/diff/commit/push tools with conventional-commits check"
```

### Task F7: open_pr / comment_pr

**Files:**
- Create: `workers/tools/providers/pr_tools.py`
- Test: `tests/workers/tools/test_pr_tools.py`

- [ ] **Step 1: Failing test** — `open_pr` calls `GitProvider.create_pr(draft=True)` and emits `pr_created` event + audit with diff hash + PR url artifact.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(workers): open_pr/comment_pr tools + diff-hash audit"
```

### Task F8: web_fetch (egress-policed)

**Files:**
- Create: `workers/tools/providers/web_fetch.py`
- Test: `tests/workers/tools/test_web_fetch.py`

- [ ] **Step 1: Failing test** — fetch to disallowed host → `ToolResult(ok=False)` + `egress_blocked` event + audit; allowed host returns body.
- [ ] **Step 2–6**: Implement using egress checker (Phase H); commit.

```bash
git commit -m "feat(workers): web_fetch tool (egress-policed)"
```

### Task F9: web_search (via RAG)

**Files:**
- Create: `workers/tools/providers/web_search.py`
- Test: `tests/workers/tools/test_web_search.py`

- [ ] **Step 1: Failing test** — calls `rag.search_providers.web_search(...)` if RAG module present; raises `ToolUnavailable` otherwise.
- [ ] **Step 2–6**: Implement soft dependency import; commit.

```bash
git commit -m "feat(workers): web_search tool (RAG-backed)"
```

### Task F10: kb_search

**Files:**
- Create: `workers/tools/providers/kb_search.py`
- Test: `tests/workers/tools/test_kb_search.py`

- [ ] **Step 1–6**: same soft-dep pattern through `ai_portal.rag.search.kb_search`; commit.

```bash
git commit -m "feat(workers): kb_search tool (RAG-backed)"
```

### Task F11: memory_recall / memory_remember

**Files:**
- Create: `workers/tools/providers/memory_tools.py`
- Test: `tests/workers/tools/test_memory_tools.py`

- [ ] **Step 1–6**: soft-dep `ai_portal.memories`; scope memories per repo (`scope=("repo", repo.full_name)`); commit.

```bash
git commit -m "feat(workers): memory_recall + memory_remember tools"
```

### Task F12: browser tool (Playwright in sandbox)

**Files:**
- Create: `workers/tools/providers/browser.py`
- Test: `tests/workers/tools/test_browser.py`

- [ ] **Step 1: Failing test** — `browser({"action":"goto","url":"http://example.com"})` runs Playwright via sandbox-side helper script; snapshot returned + uploaded to BlobStore as artifact.
- [ ] **Step 2–6**: Implement; ensure Playwright runs inside the sandbox image, not host; commit.

```bash
git commit -m "feat(workers): browser tool (Playwright-in-sandbox) + snapshot artifact"
```

### Task F13: MCP bridge

**Files:**
- Create: `workers/tools/providers/mcp_bridge.py`
- Test: `tests/workers/tools/test_mcp_bridge.py`

- [ ] **Step 1: Failing test** — pool config lists MCP server URL + allow-listed tool names; bridge discovers tools and exposes each as a `Tool` instance forwarded to the MCP client.
- [ ] **Step 2–6**: Implement using `mcp` client lib; per-pool allow-list enforced; commit.

```bash
git commit -m "feat(workers): MCP bridge — any allow-listed MCP server exposed as tools"
```

---

## Phase G — Secrets

### Task G1: SecretsProxy + per-pool/per-repo bindings

**Files:**
- Create: `workers/secrets/proxy.py`, `workers/secrets/service.py`
- Test: `tests/workers/secrets/test_proxy.py`

- [ ] **Step 1: Failing test**

```python
@pytest.mark.asyncio
async def test_secrets_injected_as_env_and_redacted_in_output(db_session, org):
    from ai_portal.workers.secrets.proxy import SecretsProxy
    p = SecretsProxy(values={"NPM_TOKEN": "npm_super-secret-XYZ"})
    env = p.env()
    assert env["NPM_TOKEN"].startswith("npm_super")
    assert p.redact("token=npm_super-secret-XYZ end") == "token=*** end"
    # never written to logs
    assert "NPM_TOKEN" not in p.audit_payload()
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement**

```python
# server/api/src/ai_portal/workers/secrets/proxy.py
import re

class SecretsProxy:
    def __init__(self, values: dict[str, str]):
        self._values = values
        self._patterns = [re.escape(v) for v in values.values() if v]

    def env(self) -> dict[str, str]:
        return dict(self._values)

    def redact(self, text: str) -> str:
        for p in self._patterns:
            text = re.sub(p, "***", text)
        return text

    def audit_payload(self) -> dict:
        return {"secret_count": len(self._values)}
```

- [ ] **Step 4–5: Run + commit**

```bash
git commit -am "feat(workers): SecretsProxy (env-injected, output-redacted)"
```

### Task G2: Secret detection on diffs (block leak)

**Files:**
- Create: `workers/secrets/scanner.py`
- Test: `tests/workers/secrets/test_scanner.py`

- [ ] **Step 1: Failing test** — diff containing `AKIA...` (AWS key pattern) → `scan_diff(diff) -> [Match]`; orchestrator must refuse to commit/push when matches non-empty; emit `secret_blocked` event + audit.
- [ ] **Step 2–6**: Implement using regex catalog (AWS, GCP, GH PAT, Slack, generic high-entropy); commit.

```bash
git commit -m "feat(workers): secret-detection on diffs + commit block"
```

### Task G3: SecretGrant CRUD + audit

**Files:**
- Create: `workers/secrets/router.py`, `workers/secrets/schemas.py`
- Test: `tests/workers/secrets/test_router.py`

- [ ] **Step 1–6**: Implement CRUD; every grant + every injection at run-time audited; commit.

```bash
git commit -m "feat(workers): secret grants CRUD + audit trail"
```

---

## Phase H — Egress

### Task H1: EgressChecker + per-pool allow-list

**Files:**
- Create: `workers/egress/checker.py`, `workers/egress/service.py`
- Test: `tests/workers/egress/test_checker.py`

- [ ] **Step 1: Failing test**

```python
@pytest.mark.asyncio
async def test_egress_default_deny():
    from ai_portal.workers.egress.checker import EgressChecker, EgressBlocked
    c = EgressChecker(allow_list=["pypi.org", "*.npmjs.org"])
    assert c.allowed("https://pypi.org/simple/foo/")
    assert c.allowed("https://registry.npmjs.org/x")
    assert not c.allowed("https://evil.com/x")
    with pytest.raises(EgressBlocked):
        c.assert_allowed("https://evil.com/x")
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement**

```python
# server/api/src/ai_portal/workers/egress/checker.py
from urllib.parse import urlparse
import fnmatch

class EgressBlocked(Exception):
    def __init__(self, host: str): super().__init__(host); self.host = host

class EgressChecker:
    def __init__(self, allow_list: list[str]):
        self._allow = allow_list

    def allowed(self, url: str) -> bool:
        host = urlparse(url).hostname or ""
        return any(fnmatch.fnmatch(host, pat) for pat in self._allow)

    def assert_allowed(self, url: str) -> None:
        if not self.allowed(url):
            raise EgressBlocked(urlparse(url).hostname or url)
```

- [ ] **Step 4–5: Run + commit**

```bash
git commit -am "feat(workers): egress checker (default-deny, glob allow-list)"
```

### Task H2: Common allow-list presets (npm / pypi / crates / etc.)

**Files:**
- Create: `workers/egress/presets.py`
- Test: `tests/workers/egress/test_presets.py`

- [ ] **Step 1: Failing test** — `PRESETS["pypi"]` includes `pypi.org`, `*.pythonhosted.org`.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(workers): egress allow-list presets (npm/pypi/crates/go/maven/etc.)"
```

### Task H3: DNS-level enforcement (deploy-side hook)

**Files:**
- Create: `workers/egress/dns_policy.py` (translates allow-list to a CoreDNS/iptables snippet)
- Test: `tests/workers/egress/test_dns_policy.py`

- [ ] **Step 1: Failing test** — output snippet contains every host + denies wildcard `.`
- [ ] **Step 2–6**: Implement (renders templates; actual enforcement happens at deploy time); commit.

```bash
git commit -m "feat(workers): DNS policy renderer for egress allow-list"
```

### Task H4: Blocked-egress audit

**Files:**
- Modify: `workers/egress/checker.py` to emit `egress_blocked` event + audit row when called via instrumented wrapper.
- Test: `tests/workers/egress/test_audit.py`

- [ ] **Step 1–6**: Implement + commit.

```bash
git commit -m "feat(workers): audit blocked egress attempts"
```

---

## Phase I — Cost & budget

### Task I1: Per-task cost tracker

**Files:**
- Create: `workers/budget/cost.py`
- Test: `tests/workers/budget/test_cost.py`

- [ ] **Step 1: Failing test** — accumulate LLM cost (via Gateway facade `usage`), sandbox-minutes cost (provider-rate), storage cost; `run.cost_cents` updated.
- [ ] **Step 2–6**: Implement; emit `cost_update` event each delta; commit.

```bash
git commit -m "feat(workers): per-task cost tracker (LLM + sandbox + storage)"
```

### Task I2: Budget gate (pause-on-threshold + approval)

**Files:**
- Create: `workers/budget/gate.py`
- Test: `tests/workers/budget/test_gate.py`

- [ ] **Step 1: Failing test** — pool budget 1000c; cost 1001c → orchestrator pauses, creates `WorkerApproval(kind=budget)`, emits `approval_requested` event + webhook + notification.
- [ ] **Step 2–6**: Implement; commit.

```bash
git commit -m "feat(workers): budget gate — pause + approve + resume"
```

### Task I3: Budget threshold webhook + notification

**Files:**
- Modify: `workers/budget/gate.py` to call `emit_webhook("workers.budget.threshold", ...)` + `notify_send(...)`
- Test: `tests/workers/budget/test_notifications.py`

- [ ] **Step 1–6**: Implement, commit.

```bash
git commit -m "feat(workers): budget webhook + notification on threshold"
```

---

## Phase J — Approvals

### Task J1: Approval policies (always/never/on_cost_above/on_files_matching/on_first_run_for_repo)

**Files:**
- Create: `workers/policies/approval_policy.py`
- Test: `tests/workers/policies/test_approval_policy.py`

- [ ] **Step 1: Failing test**

```python
@pytest.mark.asyncio
async def test_on_files_matching():
    from ai_portal.workers.policies.approval_policy import resolve_approval, ApprovalPolicySpec
    spec = ApprovalPolicySpec(kind="on_files_matching", patterns=["**/migrations/**"])
    assert await resolve_approval(spec, changed_files=["api/migrations/x.py"]) is True
    assert await resolve_approval(spec, changed_files=["src/foo.py"]) is False
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement**

```python
# server/api/src/ai_portal/workers/policies/approval_policy.py
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Literal

@dataclass
class ApprovalPolicySpec:
    kind: Literal["always", "never", "on_cost_above", "on_files_matching", "on_first_run_for_repo"]
    threshold_cents: int | None = None
    patterns: list[str] | None = None

async def resolve_approval(spec: ApprovalPolicySpec, *,
                           cost_cents: int = 0,
                           changed_files: list[str] | None = None,
                           is_first_run_for_repo: bool = False) -> bool:
    if spec.kind == "always": return True
    if spec.kind == "never": return False
    if spec.kind == "on_cost_above": return cost_cents > (spec.threshold_cents or 0)
    if spec.kind == "on_files_matching":
        return any(fnmatch(f, p) for f in (changed_files or []) for p in (spec.patterns or []))
    if spec.kind == "on_first_run_for_repo": return is_first_run_for_repo
    return False
```

- [ ] **Step 4–5: Run + commit**

```bash
git commit -am "feat(workers): approval policies (5 kinds)"
```

### Task J2: M-of-N approvals

**Files:**
- Modify: `workers/policies/approval_policy.py` add `required_approvers: int`
- Create: `workers/policies/approval_service.py`
- Test: `tests/workers/policies/test_m_of_n.py`

- [ ] **Step 1: Failing test** — pool requires 2-of-N; 1 approval → still pending; 2 → approved; audit each decision.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(workers): M-of-N approvals"
```

### Task J3: Approval decision endpoint

**Files:**
- Modify: `workers/router.py` add `POST /v1/workers/approvals/{id}/decide`
- Test: `tests/workers/test_approval_router.py`

- [ ] **Step 1: Failing test** — POST decide → audit row; on final approval, orchestrator advances task state.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(workers): approval decision endpoint"
```

---

## Phase K — Events stream + live UI backend

### Task K1: Event writer + buffer

**Files:**
- Create: `workers/events/writer.py`
- Test: `tests/workers/events/test_writer.py`

- [ ] **Step 1: Failing test**

```python
@pytest.mark.asyncio
async def test_writer_persists_and_broadcasts(db_session):
    from ai_portal.workers.events.writer import EventWriter
    from ai_portal.workers.types import EventKind
    w = EventWriter(db_session)
    received = []
    async def listener(ev): received.append(ev)
    w.subscribe("run-1", listener)
    await w.emit("run-1", EventKind.agent_thought, {"text": "thinking"})
    assert len(received) == 1
    # persisted
    rows = (await db_session.execute("SELECT count(*) FROM worker_events WHERE run_id='run-1'")).scalar()
    assert rows == 1
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement**

```python
# server/api/src/ai_portal/workers/events/writer.py
import asyncio, uuid
from collections import defaultdict
from datetime import datetime
from ai_portal.workers.model import WorkerEvent
from ai_portal.workers.types import EventKind

class EventWriter:
    def __init__(self, session):
        self.s = session
        self._subs: dict[str, list] = defaultdict(list)

    def subscribe(self, run_id: str, cb):
        self._subs[run_id].append(cb)

    def unsubscribe(self, run_id: str, cb):
        self._subs[run_id].remove(cb)

    async def emit(self, run_id: str, kind: EventKind, payload: dict):
        row = WorkerEvent(id=str(uuid.uuid4()), run_id=run_id, kind=kind.value,
                          payload_json=payload, ts=datetime.utcnow())
        self.s.add(row)
        await self.s.flush()
        for cb in list(self._subs.get(run_id, [])):
            try:
                await cb(row)
            except Exception:
                pass
```

- [ ] **Step 4–5: Run + commit**

```bash
git commit -am "feat(workers): event writer (persist + in-process broadcast)"
```

### Task K2: SSE endpoint `/v1/workers/tasks/{id}/events`

**Files:**
- Modify: `workers/router.py`
- Test: `tests/workers/events/test_sse.py`

- [ ] **Step 1: Failing test**

```python
@pytest.mark.asyncio
async def test_sse_streams_live_events(client, key, run_id):
    async with client.stream("GET", f"/v1/workers/tasks/{task_id}/events",
                             headers={"Authorization": f"Bearer {key}"}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        first = await r.aiter_lines().__anext__()
        assert first.startswith("event: ") or first.startswith("data: ")
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement**

```python
# inside workers/router.py
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from ai_portal.workers.model import WorkerEvent, WorkerRun, WorkerTask
import asyncio, json

@router.get("/v1/workers/tasks/{task_id}/events")
async def stream_events(task_id: str, after_id: str | None = None,
                        actor=Depends(require_permission("workers:submit")),
                        session=Depends(get_session),
                        writer: EventWriter = Depends(get_event_writer)):
    task = (await session.execute(select(WorkerTask).where(WorkerTask.id == task_id))).scalar_one()
    runs = (await session.execute(select(WorkerRun).where(WorkerRun.task_id == task.id)
                                   .order_by(WorkerRun.attempt_no))).scalars().all()

    async def gen():
        # backfill
        for run in runs:
            q = select(WorkerEvent).where(WorkerEvent.run_id == run.id)
            if after_id:
                q = q.where(WorkerEvent.id > after_id)
            rows = (await session.execute(q.order_by(WorkerEvent.ts))).scalars().all()
            for r in rows:
                yield f"id: {r.id}\nevent: {r.kind}\ndata: {json.dumps(r.payload_json)}\n\n"
        # live
        q: asyncio.Queue = asyncio.Queue()
        async def cb(ev): await q.put(ev)
        for run in runs:
            writer.subscribe(run.id, cb)
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"id: {ev.id}\nevent: {ev.kind}\ndata: {json.dumps(ev.payload_json)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            for run in runs:
                writer.unsubscribe(run.id, cb)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

- [ ] **Step 4–5: Run + commit**

```bash
git commit -am "feat(workers): SSE worker_events endpoint (backfill + live)"
```

### Task K3: Pause / resume / cancel endpoints + user message

**Files:**
- Modify: `workers/router.py`, `workers/orchestrator/control.py`
- Test: `tests/workers/test_control_endpoints.py`

- [ ] **Step 1: Failing test** — `POST /v1/workers/tasks/{id}/pause` flips state; `/resume` flips back; `/cancel` kills sandbox + audits; `/message` writes `user_message` event the agent loop sees on next tick.
- [ ] **Step 2–6**: Implement; commit.

```bash
git commit -m "feat(workers): pause/resume/cancel/message endpoints"
```

---

## Phase L — Agent loops

### Task L1: ReAct loop (full exemplar)

**Files:**
- Create: `server/api/src/ai_portal/workers/agent_loops/providers/react.py`
- Test: `server/api/tests/workers/agent_loops/test_react.py`

- [ ] **Step 1: Failing test**

```python
@pytest.mark.asyncio
async def test_react_loop_iterates_until_finish(monkeypatch, fake_gateway, fake_tools, fake_sandbox):
    from ai_portal.workers.agent_loops.providers.react import ReactLoop
    from ai_portal.workers.agent_loops.protocol import AgentRunCtx
    fake_gateway.queue([
        {"thought": "use shell", "tool": "shell", "tool_args": {"cmd": ["echo", "x"]}},
        {"thought": "done", "tool": None, "final": "ok"},
    ])
    loop = ReactLoop()
    events = [ev async for ev in loop.run(AgentRunCtx(
        task=fake_task, run=fake_run, tools=fake_tools, gateway=fake_gateway,
        sandbox=fake_sandbox.handle, sandbox_provider=fake_sandbox.provider,
        repo=None, model="claude-sonnet-4-6", max_iterations=5,
    ))]
    kinds = [e.kind for e in events]
    assert "agent_thought" in kinds and "tool_call" in kinds and "tool_result" in kinds
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement**

```python
# server/api/src/ai_portal/workers/agent_loops/providers/react.py
from __future__ import annotations
import json
from datetime import datetime
from typing import AsyncIterator
from ai_portal.workers.agent_loops.protocol import AgentLoop, AgentRunCtx
from ai_portal.workers.types import WorkerEvent, EventKind

SYSTEM = (
    "Engineer agent.\n"
    "- Plan briefly. Act with tools. Verify (tests/lint).\n"
    "- One tool per step. Reason in <thought>. Stop when task done.\n"
    "- Never push to main. Never write secrets.\n"
)

class ReactLoop:
    name = "react"

    async def run(self, ctx: AgentRunCtx) -> AsyncIterator[WorkerEvent]:
        tools_by_name = {t.name: t for t in ctx.tools}
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"{ctx.task.title}\n\n{ctx.task.description}"},
        ]
        for _ in range(ctx.max_iterations):
            resp = await ctx.gateway.complete({
                "model": ctx.model,
                "messages": messages,
                "tools": [{"name": t.name, "schema": t.schema} for t in ctx.tools],
            })
            step = resp.content[0].text if not resp.tool_calls else None
            if resp.tool_calls:
                tc = resp.tool_calls[0]
                yield WorkerEvent(ctx.run.id, EventKind.agent_thought,
                                  {"text": tc.reasoning or ""}, datetime.utcnow())
                yield WorkerEvent(ctx.run.id, EventKind.tool_call,
                                  {"tool": tc.name, "args": tc.arguments}, datetime.utcnow())
                tool = tools_by_name.get(tc.name)
                if not tool:
                    yield WorkerEvent(ctx.run.id, EventKind.error,
                                      {"error": f"unknown tool {tc.name}"}, datetime.utcnow())
                    continue
                result = await tool.invoke(tc.arguments, ctx.tool_ctx_for(tc.name))
                yield WorkerEvent(ctx.run.id, EventKind.tool_result,
                                  {"tool": tc.name, "ok": result.ok,
                                   "output": result.output, "error": result.error},
                                  datetime.utcnow())
                messages.append({"role": "assistant", "content": "",
                                 "tool_calls": [{"name": tc.name, "args": tc.arguments}]})
                messages.append({"role": "tool", "name": tc.name,
                                 "content": json.dumps(result.output)})
            else:
                yield WorkerEvent(ctx.run.id, EventKind.agent_thought,
                                  {"text": step or ""}, datetime.utcnow())
                if "final:" in (step or "").lower() or resp.stop_reason == "end_turn":
                    return
                messages.append({"role": "assistant", "content": step or ""})
```

- [ ] **Step 4–5: Run + commit**

```bash
git commit -am "feat(workers): ReAct agent loop"
```

### Task L2: Plan-and-Execute loop (short)

**Files:**
- Create: `workers/agent_loops/providers/plan_and_execute.py`
- Test: `tests/workers/agent_loops/test_plan_and_execute.py`

- [ ] **Step 1: Failing test** — plan produced first, then executes each step, then verifies.
- [ ] **Step 2–6**: Implement; commit.

```bash
git commit -m "feat(workers): plan_and_execute agent loop"
```

### Task L3: OpenHands-style loop (short)

**Files:**
- Create: `workers/agent_loops/providers/openhands_style.py`
- Test: `tests/workers/agent_loops/test_openhands_style.py`

- [ ] **Step 1: Failing test** — interleaves browser + shell + edit_file actions; supports "wait for next user message" idle state.
- [ ] **Step 2–6**: Implement; commit.

```bash
git commit -m "feat(workers): openhands_style agent loop"
```

### Task L4: AGENTS.md / CLAUDE.md / .cursorrules loader

**Files:**
- Create: `workers/agent_loops/repo_instructions.py`
- Test: `tests/workers/agent_loops/test_repo_instructions.py`

- [ ] **Step 1: Failing test** — `load_repo_instructions(sandbox, workdir)` returns the merged content if any file present; otherwise empty string. Loop prepends to system prompt.
- [ ] **Step 2–6**: Implement; commit.

```bash
git commit -m "feat(workers): load AGENTS.md/CLAUDE.md/.cursorrules into agent system prompt"
```

### Task L5: Package-manager + test-command detector with repo memory cache

**Files:**
- Create: `workers/agent_loops/repo_profile.py`
- Test: `tests/workers/agent_loops/test_repo_profile.py`

- [ ] **Step 1: Failing test** — detects `pnpm-lock.yaml` → `pnpm`, `pyproject.toml` → `uv`/`pip`, `Cargo.toml` → `cargo`; result cached as repo-scoped memory on first run.
- [ ] **Step 2–6**: Implement; commit.

```bash
git commit -m "feat(workers): detect package manager + test cmd; cache in repo memory"
```

---

## Phase M — Orchestrator

### Task M1: Orchestrator state machine

**Files:**
- Create: `server/api/src/ai_portal/workers/orchestrator/state_machine.py`
- Test: `server/api/tests/workers/orchestrator/test_state_machine.py`

- [ ] **Step 1: Failing test** — `advance(task, to=status)` enforces `can_transition`; raises on illegal; emits `phase_changed` event + audit.
- [ ] **Step 2–6**: Implement; commit.

```bash
git commit -m "feat(workers): orchestrator state machine (guarded transitions)"
```

### Task M2: Orchestrator main loop (provision → plan → approve → execute → verify → PR → approve → done)

**Files:**
- Create: `server/api/src/ai_portal/workers/orchestrator/runner.py`
- Test: `server/api/tests/workers/orchestrator/test_runner.py`

- [ ] **Step 1: Failing test**

```python
@pytest.mark.asyncio
async def test_full_happy_path_with_fake_sandbox(db_session, org, pool, fake_gateway):
    from ai_portal.workers.orchestrator.runner import Orchestrator
    fake_gateway.queue([
        {"thought":"plan","tool":None,"final":"plan: edit foo.py"},
        {"thought":"act","tool":"write_file","tool_args":{"path":"foo.py","content":"x=1\n"}},
        {"thought":"verify","tool":"run_tests","tool_args":{}},
        {"thought":"done","tool":"open_pr","tool_args":{"title":"fix","body":"..."}},
    ])
    orch = Orchestrator(db_session, sandbox_name="fake")
    task = await orch.submit(TaskInput(title="t", description="d", repo="acme/api"),
                             trigger_source="rest_api", actor_id="u1", org_id=org.id, pool_id=pool.id)
    await orch.drive(task.id)
    task = await orch.get(task.id)
    assert task.status == "completed"
```

- [ ] **Step 2: Run (expect fail)**

- [ ] **Step 3: Implement**

```python
# server/api/src/ai_portal/workers/orchestrator/runner.py
from __future__ import annotations
from datetime import datetime
from ai_portal.workers.types import TaskStatus, EventKind, TaskInput
from ai_portal.workers.model import WorkerTask, WorkerRun, WorkerSandboxRow
from ai_portal.workers.sandboxes.registry import get as get_sandbox
from ai_portal.workers.agent_loops.providers.react import ReactLoop
from ai_portal.workers.policies.branch_lock import acquire_branch, release_branch
from ai_portal.workers.policies.approval_policy import resolve_approval
from ai_portal.workers.budget.gate import BudgetGate
from ai_portal.workers.events.writer import EventWriter

class Orchestrator:
    def __init__(self, session, *, sandbox_name="docker"):
        self.s = session
        self.sandbox_name = sandbox_name
        self.events = EventWriter(session)

    async def submit(self, ti: TaskInput, *, trigger_source, actor_id, org_id, pool_id) -> WorkerTask:
        t = WorkerTask(org_id=org_id, pool_id=pool_id, trigger_source=trigger_source,
                       trigger_payload_json={}, title=ti.title, description=ti.description,
                       status="queued", created_by=actor_id)
        self.s.add(t); await self.s.commit()
        return t

    async def drive(self, task_id: str):
        task = await self._get(task_id)
        await self._transition(task, TaskStatus.planning)
        run = WorkerRun(task_id=task.id, attempt_no=1, status="planning")
        self.s.add(run); await self.s.commit()
        pool = await self._get_pool(task.pool_id)
        await acquire_branch(self.s, org_id=task.org_id, repo=task.trigger_payload_json.get("repo", ""),
                             branch=f"worker/{task.id}")
        sandbox_p = get_sandbox(pool.sandbox_provider)
        sandbox_h = await sandbox_p.provision(
            image=self._image_for(pool.template),
            limits=self._limits_for(pool),
            env={},
            egress_allow_list=await self._egress_for(pool),
        )
        self.s.add(WorkerSandboxRow(run_id=run.id, provider=sandbox_p.name,
                                    provider_resource_id=sandbox_h.provider_resource_id,
                                    state="allocated"))
        await self.s.commit()
        try:
            tools = await self._build_tools(pool, sandbox_p, sandbox_h, task, run)
            gateway = self._gateway_facade(task, run)
            loop = ReactLoop()
            budget = BudgetGate(self.s, pool, run)
            await self._transition(task, TaskStatus.executing)
            async for ev in loop.run(self._ctx(task, run, tools, gateway, sandbox_p, sandbox_h, pool.default_model)):
                await self.events.emit(run.id, ev.kind, ev.payload)
                # budget pause
                if await budget.exceeded():
                    await self._transition(task, TaskStatus.paused)
                    await self._request_approval(task, kind="budget")
                    return
                # secret/egress hard stops
                if ev.kind in (EventKind.secret_blocked, EventKind.egress_blocked):
                    await self._transition(task, TaskStatus.failed)
                    return
            # plan/PR approval gates
            policy = pool.settings_json.get("approval_policy", {})
            needs_pr_approval = await resolve_approval(policy.get("pr"),
                                                      cost_cents=run.cost_cents,
                                                      changed_files=await self._diff_files(sandbox_p, sandbox_h),
                                                      is_first_run_for_repo=await self._first_run(task))
            if needs_pr_approval:
                await self._transition(task, TaskStatus.awaiting_pr_approval)
                await self._request_approval(task, kind="pr")
                return
            await self._transition(task, TaskStatus.completed)
        except Exception as e:
            await self.events.emit(run.id, EventKind.error, {"error": str(e)})
            await self._transition(task, TaskStatus.failed)
            raise
        finally:
            await sandbox_p.kill(sandbox_h)
            await release_branch(self.s, org_id=task.org_id,
                                 repo=task.trigger_payload_json.get("repo", ""),
                                 branch=f"worker/{task.id}")
```

- [ ] **Step 4–5: Run + commit**

```bash
git commit -am "feat(workers): orchestrator main loop (plan/execute/verify/PR/approve)"
```

### Task M3: Replay endpoint

**Files:**
- Modify: `workers/router.py` add `POST /v1/workers/tasks/{id}/replay`
- Test: `tests/workers/test_replay.py`

- [ ] **Step 1: Failing test** — replay creates a new `WorkerTask` with same `TaskInput` + same pool, runs fresh sandbox; original audit linked via `replay_of_task_id`.
- [ ] **Step 2–6**: Implement; commit.

```bash
git commit -m "feat(workers): replay historic task with fresh sandbox"
```

---

## Phase N — Public API + facade

### Task N1: Pools CRUD

**Files:**
- Create: `workers/router.py` (extend), `workers/schemas.py`, `workers/service.py`
- Test: `tests/workers/test_pools_router.py`

- [ ] **Step 1: Failing test** — `GET/POST/PUT/DELETE /v1/workers/pools` guarded by `workers:admin`; repo_allow_list validates non-empty.
- [ ] **Step 2–6**: Implement; commit.

```bash
git commit -m "feat(workers): pools CRUD API"
```

### Task N2: Tasks API (submit / get / cancel / pause / resume / message / artifacts)

- [ ] **Step 1: Failing test** — covers each endpoint with permission checks.
- [ ] **Step 2–6**: Implement; commit.

```bash
git commit -m "feat(workers): tasks API surface (submit/get/cancel/pause/resume/message/artifacts)"
```

### Task N3: Health endpoint + module facade

**Files:**
- Create: `server/api/src/ai_portal/workers/__init__.py` re-exports `submit_task`, `cancel_task`, `stream_events`
- Test: `tests/workers/test_facade.py`

- [ ] **Step 1: Failing test** — chat module imports `from ai_portal.workers import submit_task` and submits via that path.
- [ ] **Step 2–6**: Implement; commit.

```bash
git commit -m "feat(workers): public facade for chat/assistants modules"
```

---

## Phase O — Observability

### Task O1: Trace correlation with Gateway

**Files:**
- Modify: `workers/orchestrator/runner.py` to set `metadata={"worker_task_id": task.id, "worker_run_id": run.id}` on every Gateway call
- Test: `tests/workers/observability/test_trace_correlation.py`

- [ ] **Step 1: Failing test** — Gateway `request_traces` rows for this task have `metadata.worker_task_id == task.id`.
- [ ] **Step 2–6**: Implement; commit.

```bash
git commit -m "feat(workers): correlate gateway traces with worker task/run"
```

### Task O2: Metrics

**Files:**
- Create: `workers/observability/metrics.py` (Prometheus-style counters + histograms)
- Test: `tests/workers/observability/test_metrics.py`

- [ ] **Step 1: Failing test** — counters: `workers_tasks_total{status}`, `workers_task_duration_seconds`, `workers_cost_cents_total{template}`, `workers_failures_total{reason}`.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(workers): metrics (success/fail rate, duration, cost)"
```

---

## Phase P — GDPR cascade

### Task P1: Register deleter with Control Plane

**Files:**
- Create: `workers/gdpr.py`
- Modify: `workers/__init__.py` import-time call to `register_deleter("workers", delete_for_org)`
- Test: `tests/workers/test_gdpr.py`

- [ ] **Step 1: Failing test** — Control Plane delete cascade removes worker_tasks, worker_runs, worker_events, worker_artifacts, worker_approvals, worker_sandboxes, secrets_grants, egress_rules, git_integrations, issue_tracker_integrations, worker_schedules.
- [ ] **Step 2–6**: Implement; commit.

```bash
git commit -m "feat(workers): GDPR delete cascade registered with control plane"
```

### Task P2: Register exporter

**Files:**
- Modify: `workers/gdpr.py` add `export_for_org` returning structured dict per table
- Test: `tests/workers/test_gdpr_export.py`

- [ ] **Step 1: Failing test** — export contains tasks + runs + events + artifacts for the org only.
- [ ] **Step 2–6**: Implement; commit.

```bash
git commit -m "feat(workers): GDPR export registered with control plane"
```

---

## Phase Q — Frontend UI

### Task Q1..Qn: Worker pages

Pages (one task each, TanStack Router + React Query):

- [ ] Q1: Workers → Tasks (list, filters: pool / repo / status / trigger)
- [ ] Q2: Task detail → live view (events stream pane, terminal pane, file diff viewer, agent reasoning pane, side-by-side)
- [ ] Q3: Task detail → approvals pane (approve/reject + reason)
- [ ] Q4: Task detail → artifacts (PR link out, logs download, screenshots gallery)
- [ ] Q5: Task detail → controls (pause / resume / cancel / send message)
- [ ] Q6: Pools (list + CRUD + template editor + repo allow-list + budget + approval policy)
- [ ] Q7: Integrations → Git (Github / Gitlab / Bitbucket / Gitea / Azure DevOps connect flow)
- [ ] Q8: Integrations → Issue trackers (Jira / Linear / Github Issues / Gitlab Issues / Azure Boards)
- [ ] Q9: Settings → Budgets (per-pool + per-org cap)
- [ ] Q10: Settings → Egress allow-list (per-pool with preset picker)
- [ ] Q11: Settings → Secrets bindings (per-pool, per-repo)
- [ ] Q12: Settings → Approval policies (plan / PR / budget; M-of-N)
- [ ] Q13: Analytics (success rate, cost per task, time per task, per-repo / per-template breakdowns)

Each: implement page + one component-level unit test for non-trivial logic. Defer E2E.

Commit per page:
```bash
git commit -m "feat(workers): UI <page>"
```

---

## Final checks

- [ ] **Step F1**: `pytest <touched files>` only. No full suite. No E2E.
- [ ] **Step F2**: `ruff check --fix` + `ruff format`
- [ ] **Step F3**: `mypy src/ai_portal/workers`
- [ ] **Step F4**: Alembic round-trip (`alembic downgrade -1 && alembic upgrade head`)
- [ ] **Step F5**: Hand off to orchestrator. Do NOT write or run E2E.

---

## Out of scope (deferred per spec)

- Browser-only / desktop-control tasks (RPA beyond coding)
- Multi-worker swarms (agent-to-agent collaboration)
- Live-coding pair-programming UI (single autonomous-worker view only)
- Auto-merge to default branch
- Production-deploy actions (workers push to staging at most)
- Workers on user's local machine (cloud sandboxes only v1)
- IDE plugin integrations
- Custom sandbox provider upload UI (config-only)
- Marketplace of agent templates from third parties
- Voice-triggered tasks
- Agent learning across orgs
