from ai_portal.chat.item_kinds import ItemKind, ItemStatus, ItemRole


def test_item_kind_values():
    assert {k.value for k in ItemKind} == {
        "user_message", "assistant_text", "llm_call", "tool_call",
        "server_tool_use", "thinking", "citation", "memory_pill",
        "turn_end", "error",
    }


def test_item_status_values():
    assert {s.value for s in ItemStatus} == {"streaming", "done", "error", "cancelled"}


def test_item_role_values():
    assert {r.value for r in ItemRole} == {"user", "assistant", "system"}
