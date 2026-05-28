"""Tests for the Firecracker sandbox stub."""

from __future__ import annotations

import pytest

from ai_portal.workers.sandboxes.protocol import SandboxProvider
from ai_portal.workers.sandboxes.providers.firecracker import (
    FirecrackerNotConfigured,
    FirecrackerSandbox,
)
from ai_portal.workers.types import ResourceLimits


def test_firecracker_satisfies_protocol() -> None:
    sb = FirecrackerSandbox()
    assert isinstance(sb, SandboxProvider)
    assert sb.name == "firecracker"


@pytest.mark.asyncio
async def test_provision_raises_when_socket_unconfigured() -> None:
    sb = FirecrackerSandbox()
    with pytest.raises(FirecrackerNotConfigured):
        await sb.provision(
            image="x", limits=ResourceLimits(), env={}, egress_allow_list=[]
        )


@pytest.mark.asyncio
async def test_provision_still_unimplemented_with_socket() -> None:
    sb = FirecrackerSandbox(firecracker_socket_path="/tmp/fc.sock")
    with pytest.raises(FirecrackerNotConfigured):
        await sb.provision(
            image="x", limits=ResourceLimits(), env={}, egress_allow_list=[]
        )


@pytest.mark.asyncio
async def test_kill_is_noop() -> None:
    sb = FirecrackerSandbox()
    # Should not raise — kill must be safe for cleanup paths.
    await sb.kill(None)  # type: ignore[arg-type]
