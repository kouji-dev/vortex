# Re-export shim — real implementation moved to chat/router.py
from ai_portal.chat.router import router  # noqa: F401
# Internal helpers re-exported for backwards compatibility (tests)
from ai_portal.chat.service import (  # noqa: F401
    _build_memory_block,
    _dispatch_tool_call,
    _should_summarize,
    _slice_window_messages,
)
# Module-level names re-exported so existing patch() calls continue to work
from ai_portal.services import rag as rag_svc  # noqa: F401
