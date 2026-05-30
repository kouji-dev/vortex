"""In-sandbox agent runner — sandbox-side half of the runtime (SCAFFOLD).

A small runner process injected into the VM on provision. The orchestrator
can't drive the agent CLI across the VM boundary, so this runner brokers
everything (see spec "In-Sandbox Agent Runner").

Responsibilities (when real):
- bootstrap on provision: install + launch the chosen agent CLI with the
  selected model + cloned repo + repo conventions (CLAUDE.md / AGENTS.md)
- own the agent process lifecycle inside the VM (start/restart/stop/health)
- bidirectional control channel to the orchestrator: pipe user messages IN,
  stream terminal stdio + structured events OUT
- surface per-step tool-permission prompts; relay accept/decline back
- report per-run signals: run start/finish, status, changed files + diffs
- normalize Claude vs Codex behind one wire protocol

This file is the **wire protocol + scaffold only**. The transport (stdio over
the sandbox exec channel, or a small local server in the VM) is a deferred
design decision (spec). Real CLI exec is stubbed with TODOs.
"""

from __future__ import annotations

import enum
import json
from dataclasses import asdict, dataclass, field
from typing import Any


class WireMsgKind(str, enum.Enum):
    """Frames on the runner ↔ orchestrator control channel."""

    # orchestrator → runner
    user_message = "user_message"       # {text}
    permission_decision = "permission_decision"  # {prompt_id, decision, ...}
    interrupt = "interrupt"
    stop = "stop"
    # runner → orchestrator
    ready = "ready"                     # runner booted, agent launched
    agent_event = "agent_event"         # one normalized AgentEvent
    permission_request = "permission_request"   # {prompt_id, tool, input, summary}
    run_signal = "run_signal"           # {run, status, changes:[...]}
    health = "health"
    log = "log"


@dataclass
class WireFrame:
    """One newline-delimited JSON frame on the control channel."""

    kind: WireMsgKind
    payload: dict[str, Any] = field(default_factory=dict)

    def encode(self) -> str:
        return json.dumps({"kind": self.kind.value, "payload": self.payload})

    @classmethod
    def decode(cls, line: str) -> "WireFrame":
        obj = json.loads(line)
        return cls(kind=WireMsgKind(obj["kind"]), payload=obj.get("payload", {}))


@dataclass
class RunnerBootSpec:
    """What the orchestrator hands the runner at injection time."""

    runtime: str          # claude | codex
    model: str
    gateway_base_url: str
    repo_url: str
    workdir: str = "/workspace/repo"
    skills: list[str] = field(default_factory=list)
    convention_files: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class InSandboxRunner:
    """Sandbox-side broker (SCAFFOLD — does not run an agent yet)."""

    def __init__(self, spec: RunnerBootSpec) -> None:
        self.spec = spec

    async def boot(self) -> None:
        """Install + launch the agent CLI, then emit ``ready``.

        TODO(agent-sdk-boundary): clone repo, install the chosen agent CLI,
        inject skills + convention files, set the gateway base_url env, launch
        the agent process, open the control channel. This is the in-VM exec
        boundary — requires a real sandbox runtime + transport.
        """
        raise NotImplementedError(
            "in-sandbox runner boot is stubbed — needs real sandbox + transport"
        )

    async def handle(self, frame: WireFrame) -> None:
        """Process one inbound control frame from the orchestrator."""
        raise NotImplementedError("in-sandbox runner handling is stubbed")
