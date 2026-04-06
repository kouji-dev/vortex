from ai_portal.schemas.conversation_settings import CapabilityToggles, ConversationSettings


def test_capability_toggles_has_new_fields():
    cap = CapabilityToggles()
    assert cap.web_search is False
    assert cap.data_query is False


def test_capability_toggles_accepts_new_fields():
    cap = CapabilityToggles(web_search=True, data_query=True)
    assert cap.web_search is True
    assert cap.data_query is True


def test_conversation_settings_roundtrip_with_new_fields():
    settings = ConversationSettings(
        capabilities=CapabilityToggles(web_search=True, data_query=False)
    )
    dumped = settings.model_dump()
    reloaded = ConversationSettings(**dumped)
    assert reloaded.capabilities.web_search is True
    assert reloaded.capabilities.data_query is False
