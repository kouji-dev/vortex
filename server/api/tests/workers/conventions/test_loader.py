"""Conventions loader — merges AGENTS.md, CLAUDE.md, .cursorrules."""

from __future__ import annotations

import pytest

from ai_portal.workers.conventions.loader import (
    CONVENTION_FILES,
    load_repo_conventions,
)
from ai_portal.workers.sandboxes.providers.fake import FakeSandbox
from ai_portal.workers.types import ResourceLimits


@pytest.mark.asyncio
async def test_returns_empty_when_no_files():
    sb = FakeSandbox()
    h = await sb.provision(
        image="x", limits=ResourceLimits(), env={}, egress_allow_list=[]
    )
    result = await load_repo_conventions(sb, h, workdir="/work")
    assert result.merged == ""
    assert result.sources == []


@pytest.mark.asyncio
async def test_loads_agents_md():
    sb = FakeSandbox()
    h = await sb.provision(
        image="x", limits=ResourceLimits(), env={}, egress_allow_list=[]
    )
    await sb.write_file(h, "/work/AGENTS.md", b"# Agents\n- use uv\n")
    result = await load_repo_conventions(sb, h, workdir="/work")
    assert "use uv" in result.merged
    assert "AGENTS.md" in result.sources


@pytest.mark.asyncio
async def test_merges_multiple_files_in_order():
    sb = FakeSandbox()
    h = await sb.provision(
        image="x", limits=ResourceLimits(), env={}, egress_allow_list=[]
    )
    await sb.write_file(h, "/work/AGENTS.md", b"agents content")
    await sb.write_file(h, "/work/CLAUDE.md", b"claude content")
    await sb.write_file(h, "/work/.cursorrules", b"cursor content")
    result = await load_repo_conventions(sb, h, workdir="/work")
    # Merge order matches CONVENTION_FILES tuple.
    expected_order = [f for f in CONVENTION_FILES if f in result.sources]
    assert result.sources == expected_order
    assert "agents content" in result.merged
    assert "claude content" in result.merged
    assert "cursor content" in result.merged
    # Each section labeled with its filename.
    assert "AGENTS.md" in result.merged
    assert "CLAUDE.md" in result.merged
    assert ".cursorrules" in result.merged


@pytest.mark.asyncio
async def test_ignores_unicode_decode_errors():
    sb = FakeSandbox()
    h = await sb.provision(
        image="x", limits=ResourceLimits(), env={}, egress_allow_list=[]
    )
    await sb.write_file(h, "/work/AGENTS.md", b"\xff\xfeok\n")
    result = await load_repo_conventions(sb, h, workdir="/work")
    # Decodes with errors='replace'; never crashes.
    assert "AGENTS.md" in result.sources
