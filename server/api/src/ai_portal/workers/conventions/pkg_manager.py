"""Detect the project's package manager + canonical commands.

Reads lockfiles / manifests from the sandbox and infers ``(pkg_manager,
language, install_cmd, test_cmd, lint_cmd, build_cmd)``. Result is cached
per ``repo_id`` so subsequent runs skip the I/O. Cache backend is
pluggable via :class:`RepoMemory` — production wires this to the
memories module; tests use :class:`InMemoryRepoMemory`.

Detection order matters: more specific lockfiles win. ``uv.lock`` beats
``poetry.lock`` beats ``requirements.txt``. ``pnpm-lock.yaml`` beats
``yarn.lock`` beats ``package-lock.json``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


# ── result type ──────────────────────────────────────────────────────────


@dataclass
class RepoProfile:
    """Detected project profile."""

    pkg_manager: str = "unknown"
    language: str = "unknown"
    install_cmd: list[str] | None = None
    test_cmd: list[str] | None = None
    lint_cmd: list[str] | None = None
    build_cmd: list[str] | None = None
    sources: list[str] = field(default_factory=list)
    cache_hit: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RepoProfile":
        return cls(**d)


# ── memory backend ───────────────────────────────────────────────────────


class RepoMemory(Protocol):
    """Tiny repo-scoped key/value store used to cache the profile."""

    async def get(self, repo_id: str, key: str) -> dict | None: ...
    async def set(self, repo_id: str, key: str, value: dict) -> None: ...


class InMemoryRepoMemory:
    """Default in-process backend — fine for tests + single-process dev."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], dict] = {}

    async def get(self, repo_id: str, key: str) -> dict | None:
        return self._store.get((repo_id, key))

    async def set(self, repo_id: str, key: str, value: dict) -> None:
        self._store[(repo_id, key)] = value


_CACHE_KEY = "pkg_manager_profile"


# ── detection rules (ordered) ────────────────────────────────────────────


_NODE_RULES: list[tuple[str, str]] = [
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("package-lock.json", "npm"),
    ("bun.lockb", "bun"),
]

_PY_RULES: list[tuple[str, str]] = [
    ("uv.lock", "uv"),
    ("poetry.lock", "poetry"),
    ("Pipfile.lock", "pipenv"),
    ("requirements.txt", "pip"),
    ("pyproject.toml", "pip"),  # fallback when no lockfile
]


_NODE_CMDS: dict[str, dict[str, list[str]]] = {
    "pnpm": {
        "install": ["pnpm", "install"],
        "test": ["pnpm", "test"],
        "lint": ["pnpm", "lint"],
        "build": ["pnpm", "build"],
    },
    "yarn": {
        "install": ["yarn", "install"],
        "test": ["yarn", "test"],
        "lint": ["yarn", "lint"],
        "build": ["yarn", "build"],
    },
    "npm": {
        "install": ["npm", "install"],
        "test": ["npm", "test"],
        "lint": ["npm", "run", "lint"],
        "build": ["npm", "run", "build"],
    },
    "bun": {
        "install": ["bun", "install"],
        "test": ["bun", "test"],
        "lint": ["bun", "lint"],
        "build": ["bun", "build"],
    },
}

_PY_CMDS: dict[str, dict[str, list[str]]] = {
    "uv": {
        "install": ["uv", "sync"],
        "test": ["uv", "run", "pytest"],
        "lint": ["uv", "run", "ruff", "check", "."],
        "build": ["uv", "build"],
    },
    "poetry": {
        "install": ["poetry", "install"],
        "test": ["poetry", "run", "pytest"],
        "lint": ["poetry", "run", "ruff", "check", "."],
        "build": ["poetry", "build"],
    },
    "pipenv": {
        "install": ["pipenv", "install"],
        "test": ["pipenv", "run", "pytest"],
        "lint": ["pipenv", "run", "ruff", "check", "."],
        "build": None,
    },
    "pip": {
        "install": ["pip", "install", "-r", "requirements.txt"],
        "test": ["pytest"],
        "lint": ["ruff", "check", "."],
        "build": None,
    },
}

_CARGO_CMDS = {
    "install": ["cargo", "fetch"],
    "test": ["cargo", "test"],
    "lint": ["cargo", "clippy", "--", "-D", "warnings"],
    "build": ["cargo", "build"],
}

_GO_CMDS = {
    "install": ["go", "mod", "download"],
    "test": ["go", "test", "./..."],
    "lint": ["golangci-lint", "run"],
    "build": ["go", "build", "./..."],
}


# ── filesystem probe ─────────────────────────────────────────────────────


async def _exists(sb_provider: Any, handle: Any, path: str) -> bool:
    try:
        await sb_provider.read_file(handle, path)
        return True
    except Exception:  # noqa: BLE001 — provider-specific not-found
        return False


# ── public api ───────────────────────────────────────────────────────────


async def detect_pkg_manager(
    sandbox_provider: Any,
    sandbox_handle: Any,
    *,
    workdir: str = "/work",
    repo_id: str | None = None,
    memory: RepoMemory | None = None,
) -> RepoProfile:
    """Return the project's package manager + canonical commands."""
    workdir = workdir.rstrip("/")

    if repo_id and memory:
        cached = await memory.get(repo_id, _CACHE_KEY)
        if cached:
            p = RepoProfile.from_dict(cached)
            p.cache_hit = True
            return p

    sources: list[str] = []

    # Node.js
    for fname, pm in _NODE_RULES:
        if await _exists(sandbox_provider, sandbox_handle, f"{workdir}/{fname}"):
            cmds = _NODE_CMDS[pm]
            profile = RepoProfile(
                pkg_manager=pm,
                language="node",
                install_cmd=cmds["install"],
                test_cmd=cmds["test"],
                lint_cmd=cmds["lint"],
                build_cmd=cmds["build"],
                sources=[fname],
            )
            await _cache(profile, repo_id, memory)
            return profile

    # Rust
    if await _exists(sandbox_provider, sandbox_handle, f"{workdir}/Cargo.toml"):
        profile = RepoProfile(
            pkg_manager="cargo",
            language="rust",
            install_cmd=_CARGO_CMDS["install"],
            test_cmd=_CARGO_CMDS["test"],
            lint_cmd=_CARGO_CMDS["lint"],
            build_cmd=_CARGO_CMDS["build"],
            sources=["Cargo.toml"],
        )
        await _cache(profile, repo_id, memory)
        return profile

    # Go
    if await _exists(sandbox_provider, sandbox_handle, f"{workdir}/go.mod"):
        profile = RepoProfile(
            pkg_manager="go",
            language="go",
            install_cmd=_GO_CMDS["install"],
            test_cmd=_GO_CMDS["test"],
            lint_cmd=_GO_CMDS["lint"],
            build_cmd=_GO_CMDS["build"],
            sources=["go.mod"],
        )
        await _cache(profile, repo_id, memory)
        return profile

    # Python — order: uv → poetry → pipenv → pip(requirements.txt) → pip(pyproject)
    for fname, pm in _PY_RULES:
        if await _exists(sandbox_provider, sandbox_handle, f"{workdir}/{fname}"):
            cmds = _PY_CMDS[pm]
            profile = RepoProfile(
                pkg_manager=pm,
                language="python",
                install_cmd=cmds["install"],
                test_cmd=cmds["test"],
                lint_cmd=cmds["lint"],
                build_cmd=cmds["build"],
                sources=[fname],
            )
            await _cache(profile, repo_id, memory)
            return profile

    profile = RepoProfile()
    await _cache(profile, repo_id, memory)
    return profile


async def _cache(
    profile: RepoProfile, repo_id: str | None, memory: RepoMemory | None
) -> None:
    if repo_id and memory:
        d = profile.to_dict()
        d["cache_hit"] = False  # never store cache_hit=True
        await memory.set(repo_id, _CACHE_KEY, d)
