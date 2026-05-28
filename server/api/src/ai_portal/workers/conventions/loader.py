"""Load repo-level agent conventions into the system prompt.

Reads (in order):
- ``AGENTS.md`` — generic agent contract (the cross-tool standard).
- ``CLAUDE.md`` — Claude-specific instructions.
- ``.cursorrules`` — Cursor-style instructions.

Each file is optional. Missing files are silently skipped. Decoding uses
``errors='replace'`` so binary trash does not crash the loader. The
result is a merged blob with per-file headers, ready for direct
injection into an agent loop's system prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CONVENTION_FILES: tuple[str, ...] = (
    "AGENTS.md",
    "CLAUDE.md",
    ".cursorrules",
)


@dataclass
class RepoConventions:
    """Merged convention text plus which files contributed."""

    merged: str = ""
    sources: list[str] = field(default_factory=list)


async def load_repo_conventions(
    sandbox_provider: Any,
    sandbox_handle: Any,
    *,
    workdir: str = "/work",
) -> RepoConventions:
    """Read any present convention files from ``workdir`` and merge them.

    The merged blob looks like::

        ## AGENTS.md
        <contents>

        ## CLAUDE.md
        <contents>

        ## .cursorrules
        <contents>
    """
    sections: list[str] = []
    sources: list[str] = []
    for fname in CONVENTION_FILES:
        path = f"{workdir.rstrip('/')}/{fname}"
        try:
            raw = await sandbox_provider.read_file(sandbox_handle, path)
        except KeyError:
            continue
        except FileNotFoundError:
            continue
        except Exception:  # noqa: BLE001 — provider-specific not-found
            continue
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        sources.append(fname)
        sections.append(f"## {fname}\n{text}")
    return RepoConventions(merged="\n\n".join(sections), sources=sources)
