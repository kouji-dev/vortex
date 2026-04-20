from decimal import Decimal

import pytest

from ai_portal.chat.llm_pricing import get_llm_rates, LlmRate, _RATES


def test_known_model_has_rates():
    r = get_llm_rates("gpt-4o")
    assert r is not None
    assert r.input_per_million > Decimal("0")


def test_unknown_model_returns_none():
    assert get_llm_rates("nonexistent-model-xyz") is None


@pytest.mark.parametrize("model_id,rate", list(_RATES.items()))
def test_all_rates_are_positive(model_id: str, rate: LlmRate):
    assert rate.input_per_million > Decimal("0"), f"{model_id}: input rate must be positive"
    assert rate.output_per_million > Decimal("0"), f"{model_id}: output rate must be positive"
    if rate.cached_input_per_million is not None:
        assert rate.cached_input_per_million <= rate.input_per_million, \
            f"{model_id}: cached input rate should not exceed input rate"
