"""Bundled tool registration — call :func:`register_bundled` at startup.

Registers the v1 tool subset:
- shell
- read_file / write_file / edit_file
- code_search
- run_tests / run_build / lint / format
- verify  (orchestrates test/lint/typecheck/build at the verify phase)
- web_fetch / web_search   (governed by per-pool egress allow-list)
- kb_search                (org KB retrieval via RAG)
- memory_recall / memory_remember
- browser                  (Playwright in sandbox; lazy-imported)
- mcp_bridge               (call allow-listed MCP servers as tools)

Per-pool allow-list (``registry.for_pool``) decides which tools an
individual pool can actually use; registration here is just the catalog.
"""

from __future__ import annotations

from ai_portal.workers.tools import registry
from ai_portal.workers.tools.providers.browser import BrowserTool
from ai_portal.workers.tools.providers.code_search import CodeSearchTool
from ai_portal.workers.tools.providers.files import (
    EditFileTool,
    ReadFileTool,
    WriteFileTool,
)
from ai_portal.workers.tools.providers.kb_search import KbSearchTool
from ai_portal.workers.tools.providers.mcp_bridge import McpBridgeTool
from ai_portal.workers.tools.providers.memory_recall import MemoryRecallTool
from ai_portal.workers.tools.providers.memory_remember import MemoryRememberTool
from ai_portal.workers.tools.providers.quality import (
    FormatTool,
    LintTool,
    RunBuildTool,
    RunTestsTool,
)
from ai_portal.workers.tools.providers.shell import ShellTool
from ai_portal.workers.tools.providers.verify import VerifyTool
from ai_portal.workers.tools.providers.web_fetch import WebFetchTool
from ai_portal.workers.tools.providers.web_search import WebSearchTool

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
    "web_fetch",
    "web_search",
    "kb_search",
    "memory_recall",
    "memory_remember",
    "browser",
    "mcp_bridge",
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
        WebFetchTool,
        WebSearchTool,
        KbSearchTool,
        MemoryRecallTool,
        MemoryRememberTool,
        BrowserTool,
        McpBridgeTool,
    ):
        registry.register(cls())
