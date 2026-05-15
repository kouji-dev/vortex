from enum import Enum


class ItemKind(str, Enum):
    user_message = "user_message"
    assistant_text = "assistant_text"
    llm_call = "llm_call"
    tool_call = "tool_call"
    server_tool_use = "server_tool_use"
    kb_search = "kb_search"
    thinking = "thinking"
    citation = "citation"
    memory_pill = "memory_pill"
    turn_end = "turn_end"
    error = "error"


class ItemStatus(str, Enum):
    streaming = "streaming"
    done = "done"
    error = "error"
    cancelled = "cancelled"


class ItemRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
