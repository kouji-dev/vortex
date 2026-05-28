"""Package-manager detector — lockfiles + repo-memory cache."""

from __future__ import annotations

import pytest

from ai_portal.workers.conventions.pkg_manager import (
    InMemoryRepoMemory,
    detect_pkg_manager,
)
from ai_portal.workers.sandboxes.providers.fake import FakeSandbox
from ai_portal.workers.types import ResourceLimits


async def _sandbox():
    sb = FakeSandbox()
    h = await sb.provision(
        image="x", limits=ResourceLimits(), env={}, egress_allow_list=[]
    )
    return sb, h


@pytest.mark.asyncio
async def test_detects_pnpm():
    sb, h = await _sandbox()
    await sb.write_file(h, "/work/pnpm-lock.yaml", b"lockfileVersion: 7\n")
    p = await detect_pkg_manager(sb, h, workdir="/work")
    assert p.pkg_manager == "pnpm"
    assert p.language == "node"
    assert p.install_cmd == ["pnpm", "install"]
    assert p.test_cmd == ["pnpm", "test"]


@pytest.mark.asyncio
async def test_detects_yarn():
    sb, h = await _sandbox()
    await sb.write_file(h, "/work/yarn.lock", b"")
    p = await detect_pkg_manager(sb, h, workdir="/work")
    assert p.pkg_manager == "yarn"


@pytest.mark.asyncio
async def test_detects_npm():
    sb, h = await _sandbox()
    await sb.write_file(h, "/work/package-lock.json", b"{}")
    p = await detect_pkg_manager(sb, h, workdir="/work")
    assert p.pkg_manager == "npm"


@pytest.mark.asyncio
async def test_detects_uv_over_pip():
    sb, h = await _sandbox()
    await sb.write_file(h, "/work/pyproject.toml", b"[project]\n")
    await sb.write_file(h, "/work/uv.lock", b"")
    p = await detect_pkg_manager(sb, h, workdir="/work")
    assert p.pkg_manager == "uv"
    assert p.language == "python"
    assert p.test_cmd == ["uv", "run", "pytest"]


@pytest.mark.asyncio
async def test_detects_poetry():
    sb, h = await _sandbox()
    await sb.write_file(h, "/work/poetry.lock", b"")
    await sb.write_file(h, "/work/pyproject.toml", b"[tool.poetry]\n")
    p = await detect_pkg_manager(sb, h, workdir="/work")
    assert p.pkg_manager == "poetry"


@pytest.mark.asyncio
async def test_detects_pip_fallback():
    sb, h = await _sandbox()
    await sb.write_file(h, "/work/requirements.txt", b"requests\n")
    p = await detect_pkg_manager(sb, h, workdir="/work")
    assert p.pkg_manager == "pip"
    assert p.language == "python"


@pytest.mark.asyncio
async def test_detects_cargo():
    sb, h = await _sandbox()
    await sb.write_file(h, "/work/Cargo.toml", b"")
    p = await detect_pkg_manager(sb, h, workdir="/work")
    assert p.pkg_manager == "cargo"
    assert p.language == "rust"
    assert p.test_cmd == ["cargo", "test"]


@pytest.mark.asyncio
async def test_detects_go():
    sb, h = await _sandbox()
    await sb.write_file(h, "/work/go.mod", b"module x\n")
    p = await detect_pkg_manager(sb, h, workdir="/work")
    assert p.pkg_manager == "go"
    assert p.language == "go"


@pytest.mark.asyncio
async def test_unknown_when_no_lockfile():
    sb, h = await _sandbox()
    p = await detect_pkg_manager(sb, h, workdir="/work")
    assert p.pkg_manager == "unknown"
    assert p.test_cmd is None


@pytest.mark.asyncio
async def test_cached_on_second_call():
    sb, h = await _sandbox()
    await sb.write_file(h, "/work/pnpm-lock.yaml", b"")
    mem = InMemoryRepoMemory()
    p1 = await detect_pkg_manager(sb, h, workdir="/work", repo_id="r1", memory=mem)
    assert p1.cache_hit is False
    # Remove file — second call must hit cache.
    sb._fs[h.id].pop("/work/pnpm-lock.yaml")
    p2 = await detect_pkg_manager(sb, h, workdir="/work", repo_id="r1", memory=mem)
    assert p2.pkg_manager == "pnpm"
    assert p2.cache_hit is True


@pytest.mark.asyncio
async def test_cache_keyed_per_repo():
    sb, h = await _sandbox()
    await sb.write_file(h, "/work/pnpm-lock.yaml", b"")
    mem = InMemoryRepoMemory()
    p1 = await detect_pkg_manager(sb, h, workdir="/work", repo_id="r1", memory=mem)
    assert p1.pkg_manager == "pnpm"
    # Different repo — fresh detection.
    sb2, h2 = await _sandbox()
    await sb2.write_file(h2, "/work/Cargo.toml", b"")
    p2 = await detect_pkg_manager(sb2, h2, workdir="/work", repo_id="r2", memory=mem)
    assert p2.pkg_manager == "cargo"
    assert p2.cache_hit is False
