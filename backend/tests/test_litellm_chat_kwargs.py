import pytest

from ai_portal.config import Settings
from ai_portal.services.llm_providers.litellm_chat import (
    litellm_completion_kwargs,
    normalize_litellm_model_id_for_completion,
    remap_deprecated_litellm_model,
)


def _s(**overrides: str) -> Settings:
    base = {
        "llm_api_key": "",
        "anthropic_api_key": "",
        "llm_api_base": "https://api.openai.com/v1",
    }
    base.update(overrides)
    return Settings.model_validate(base)


def test_claude_requires_anthropic_or_llm_key():
    s = _s()
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY or LLM_API_KEY"):
        litellm_completion_kwargs(s, "claude-sonnet-4-6")


def test_claude_accepts_anthropic_key():
    s = _s(anthropic_api_key="sk-ant-test")
    kw = litellm_completion_kwargs(s, "claude-sonnet-4-6")
    assert kw == {"api_key": "sk-ant-test"}


def test_claude_prefers_anthropic_over_llm_key():
    s = _s(llm_api_key="openai-key", anthropic_api_key="ant-key")
    kw = litellm_completion_kwargs(s, "claude-haiku-4-5")
    assert kw == {"api_key": "ant-key"}


def test_claude_falls_back_to_llm_key():
    s = _s(llm_api_key="shared-key")
    kw = litellm_completion_kwargs(s, "claude-opus-4-6")
    assert kw == {"api_key": "shared-key"}


def test_openai_model_requires_llm_key():
    s = _s(anthropic_api_key="sk-ant-only")
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        litellm_completion_kwargs(s, "gpt-4o-mini")


def test_openai_model_returns_key_and_base():
    s = _s(llm_api_key="sk-openai", llm_api_base="https://api.openai.com/v1")
    kw = litellm_completion_kwargs(s, "gpt-4o-mini")
    assert kw["api_key"] == "sk-openai"
    assert kw["api_base"] == "https://api.openai.com/v1"


def test_normalize_prefixes_legacy_snapshot_haiku():
    # normalize() alone only adds provider prefix; completion path uses remap first.
    assert (
        normalize_litellm_model_id_for_completion("claude-3-5-haiku-20241022")
        == "anthropic/claude-3-5-haiku-20241022"
    )


def test_remap_deprecated_haiku_snapshot_then_normalize():
    assert remap_deprecated_litellm_model("claude-3-5-haiku-20241022") == "claude-haiku-4-5"
    assert (
        normalize_litellm_model_id_for_completion(
            remap_deprecated_litellm_model("claude-3-5-haiku-20241022"),
        )
        == "anthropic/claude-haiku-4-5"
    )


def test_remap_deprecated_with_anthropic_prefix():
    assert (
        remap_deprecated_litellm_model("anthropic/claude-3-5-haiku-20241022")
        == "claude-haiku-4-5"
    )


def test_remap_deprecated_leaves_unknown_models():
    assert remap_deprecated_litellm_model("gpt-4o-mini") == "gpt-4o-mini"
    assert remap_deprecated_litellm_model("") == ""


def test_remap_legacy_opus_46_snapshot_to_alias():
    assert remap_deprecated_litellm_model("claude-opus-4-6-20260205") == "claude-opus-4-6"


def test_remap_canonical_opus_46_unchanged():
    assert remap_deprecated_litellm_model("claude-opus-4-6") == "claude-opus-4-6"


def test_remap_unversioned_opus_45_to_snapshot():
    assert remap_deprecated_litellm_model("claude-opus-4-5") == "claude-opus-4-5-20251101"


def test_normalize_prefixes_current_haiku():
    assert (
        normalize_litellm_model_id_for_completion("claude-haiku-4-5")
        == "anthropic/claude-haiku-4-5"
    )


def test_normalize_idempotent_when_anthropic_prefixed():
    mid = "anthropic/claude-haiku-4-5"
    assert normalize_litellm_model_id_for_completion(mid) == mid


def test_normalize_leaves_openai_style_models():
    assert normalize_litellm_model_id_for_completion("gpt-4o-mini") == "gpt-4o-mini"
    assert normalize_litellm_model_id_for_completion("azure/gpt-4o-mini") == "azure/gpt-4o-mini"


def test_kwargs_accepts_prefixed_anthropic_model():
    s = _s(anthropic_api_key="sk-ant")
    kw = litellm_completion_kwargs(s, "anthropic/claude-haiku-4-5")
    assert kw == {"api_key": "sk-ant"}
