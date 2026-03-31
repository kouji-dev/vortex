from ai_portal.models.memory import UserMemory


def test_user_memory_has_required_fields():
    m = UserMemory(user_id=1, content="Prefers Python", source="manual", is_active=True)
    assert m.user_id == 1
    assert m.content == "Prefers Python"
