"""Shared fixtures for worker tool tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from ai_portal.workers.sandboxes.providers.fake import FakeSandbox
from ai_portal.workers.tools.protocol import ToolContext
from ai_portal.workers.types import ResourceLimits


@dataclass
class _SecretsProxy:
    """Tiny redactor for tests — replaces every registered value with ``***``."""

    values: dict[str, str] = field(default_factory=dict)

    def redact(self, text: str) -> str:
        for v in self.values.values():
            if v:
                text = text.replace(v, "***")
        return text


@dataclass
class _TestCtx:
    """Tracks the things tools emit/audit so tests can assert on them."""

    events: list[tuple[str, dict]] = field(default_factory=list)
    audited: list[dict] = field(default_factory=list)


@pytest.fixture
def harness():
    """Returns ``(sandbox, handle, ctx, recorder)``.

    Tools receive a real :class:`ToolContext` whose ``emit_event`` /
    ``audit`` callbacks push into ``recorder``.
    """

    async def _make(
        sandbox: FakeSandbox | None = None,
        secrets: dict[str, str] | None = None,
        pool_settings: dict[str, Any] | None = None,
    ):
        sb = sandbox or FakeSandbox()
        h = await sb.provision(
            image="x",
            limits=ResourceLimits(),
            env={},
            egress_allow_list=[],
        )
        rec = _TestCtx()

        async def _emit(kind, payload):
            # ``kind`` is an EventKind enum — store .value for easy assert.
            rec.events.append((getattr(kind, "value", kind), payload))

        async def _audit(payload):
            rec.audited.append(payload)

        ctx = ToolContext(
            sandbox=h,
            sandbox_provider=sb,
            task_id="task-1",
            run_id="run-1",
            actor_id="actor-1",
            org_id="org-1",
            emit_event=_emit,
            secrets_proxy=_SecretsProxy(values=secrets or {}),
            audit=_audit,
            pool_settings=pool_settings or {},
        )
        return sb, h, ctx, rec

    return _make
