import pytest

from ai_portal.config import Settings
from ai_portal.services.llm_providers.model_routing import (
    chat_provider_credential_kwargs,
    is_langchain_anthropic_model,
    normalize_chat_model_id_for_tests,
    normalize_model_id_for_langchain_chat,
    remap_deprecated_chat_model,
)


def _s(**overrides: str) -> Settings:
    base = {
        "openai_api_key": "",
        "anthropic_api_key": "",
        "openai_api_base": "https://api.openai.com/v1",
    }
    base.update(overrides)
    return Settings.model_validate(base)


def test_claude_requires_anthropic_key():
    s = _s()
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY is not set"):
        chat_provider_credential_kwargs(s, "claude-sonnet-4-6")


def test_claude_accepts_anthropic_key():
    s = _s(anthropic_api_key="sk-ant-test")
    kw = chat_provider_credential_kwargs(s, "claude-sonnet-4-6")
    assert kw == {"api_key": "sk-ant-test"}


def test_claude_uses_anthropic_key_when_both_env_vars_set():
    s = _s(openai_api_key="openai-key", anthropic_api_key="ant-key")
    kw = chat_provider_credential_kwargs(s, "claude-haiku-4-5")
    assert kw == {"api_key": "ant-key"}


def test_claude_does_not_use_openai_key():
    s = _s(openai_api_key="shared-key")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY is not set"):
        chat_provider_credential_kwargs(s, "claude-opus-4-6")


def test_openai_model_requires_openai_key():
    s = _s(anthropic_api_key="sk-ant-only")
    with pytest.raises(ValueError, match="OPENAI_API_KEY is not set"):
        chat_provider_credential_kwargs(s, "gpt-4o-mini")


def test_openai_model_returns_key_and_base():
    s = _s(openai_api_key="sk-openai", openai_api_base="https://api.openai.com/v1")
    kw = chat_provider_credential_kwargs(s, "gpt-4o-mini")
    assert kw["api_key"] == "sk-openai"
    assert kw["api_base"] == "https://api.openai.com/v1"


def test_normalize_prefixes_legacy_snapshot_haiku():
    # normalize() alone only adds provider prefix; completion path uses remap first.
    assert (
        normalize_chat_model_id_for_tests("claude-3-5-haiku-20241022")
        == "anthropic/claude-3-5-haiku-20241022"
    )


def test_remap_deprecated_haiku_snapshot_then_normalize():
    assert (
        remap_deprecated_chat_model("claude-3-5-haiku-20241022") == "claude-haiku-4-5"
    )
    assert (
        normalize_chat_model_id_for_tests(
            remap_deprecated_chat_model("claude-3-5-haiku-20241022"),
        )
        == "anthropic/claude-haiku-4-5"
    )


def test_remap_deprecated_with_anthropic_prefix():
    assert (
        remap_deprecated_chat_model("anthropic/claude-3-5-haiku-20241022")
        == "claude-haiku-4-5"
    )


def test_remap_deprecated_leaves_unknown_models():
    assert remap_deprecated_chat_model("gpt-4o-mini") == "gpt-4o-mini"
    assert remap_deprecated_chat_model("") == ""


def test_remap_legacy_opus_46_snapshot_to_alias():
    assert remap_deprecated_chat_model("claude-opus-4-6-20260205") == "claude-opus-4-6"


def test_remap_canonical_opus_46_unchanged():
    assert remap_deprecated_chat_model("claude-opus-4-6") == "claude-opus-4-6"


def test_remap_unversioned_opus_45_to_snapshot():
    assert (
        remap_deprecated_chat_model("claude-opus-4-5") == "claude-opus-4-5-20251101"
    )


def test_normalize_prefixes_current_haiku():
    assert (
        normalize_chat_model_id_for_tests("claude-haiku-4-5")
        == "anthropic/claude-haiku-4-5"
    )


def test_normalize_idempotent_when_anthropic_prefixed():
    mid = "anthropic/claude-haiku-4-5"
    assert normalize_chat_model_id_for_tests(mid) == mid


def test_normalize_leaves_openai_style_models():
    assert normalize_chat_model_id_for_tests("gpt-4o-mini") == "gpt-4o-mini"
    assert (
        normalize_chat_model_id_for_tests("azure/gpt-4o-mini")
        == "azure/gpt-4o-mini"
    )


def test_kwargs_accepts_prefixed_anthropic_model():
    s = _s(anthropic_api_key="sk-ant")
    kw = chat_provider_credential_kwargs(s, "anthropic/claude-haiku-4-5")
    assert kw == {"api_key": "sk-ant"}


def test_catalog_slug_anthropic_claude_uses_anthropic_credentials():
    """Frontend/catalog slugs use hyphens: anthropic-claude-* not anthropic/."""
    s = _s(anthropic_api_key="sk-ant")
    kw = chat_provider_credential_kwargs(s, "anthropic-claude-haiku-4-5")
    assert kw == {"api_key": "sk-ant"}


def test_normalize_catalog_slug_to_claude_prefix():
    assert (
        normalize_model_id_for_langchain_chat("anthropic-claude-haiku-4-5")
        == "claude-haiku-4-5"
    )


def test_is_langchain_anthropic_accepts_catalog_slug():
    assert is_langchain_anthropic_model("anthropic-claude-haiku-4-5") is True


def test_langchain_normalize_strips_anthropic_prefix() -> None:
    assert (
        normalize_model_id_for_langchain_chat("anthropic/claude-haiku-4-5")
        == "claude-haiku-4-5"
    )


def test_langchain_normalize_remaps_deprecated_claude() -> None:
    assert (
        normalize_model_id_for_langchain_chat("claude-3-5-haiku-20241022")
        == "claude-haiku-4-5"
    )
