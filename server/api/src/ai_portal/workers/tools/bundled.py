"""Bundled tool registration — call :func:`register_bundled` at startup.

Registers the v1 tool subset:
- shell
- read_file / write_file / edit_file
- code_search
- run_tests / run_build / lint / format
- verify  (orchestrates test/lint/typecheck/build at the verify phase)
"""

from __future__ import annotations

from ai_portal.workers.tools import registry
from ai_portal.workers.tools.providers.code_search import CodeSearchTool
from ai_portal.workers.tools.providers.files import (
    EditFileTool,
    ReadFileTool,
    WriteFileTool,
)
from ai_portal.workers.tools.providers.quality import (
    FormatTool,
    LintTool,
    RunBuildTool,
    RunTestsTool,
)
from ai_portal.workers.tools.providers.shell import ShellTool
from ai_portal.workers.tools.providers.verify import VerifyTool

BUNDLED_TOOL_NAMES = (
    "shell",
    "read_file",
    "write_file",
    "edit_file",
    "code_search",
    "run_tests",
    "run_build",
    "lint",
    "format",
    "verify",
)


def register_bundled() -> None:
    """Register every bundled v1 tool in the global registry."""
    for cls in (
        ShellTool,
        ReadFileTool,
        WriteFileTool,
        EditFileTool,
        CodeSearchTool,
        RunTestsTool,
        RunBuildTool,
        LintTool,
        FormatTool,
        VerifyTool,
    ):
        registry.register(cls())
