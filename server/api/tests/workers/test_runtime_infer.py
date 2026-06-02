import pytest
from ai_portal.workers.runtime_infer import infer_runtime

@pytest.mark.parametrize("api_model_id, expected", [
    ("claude-opus-4-7", "claude"),
    ("claude-sonnet-4-6", "claude"),
    ("gpt-5.4-codex", "codex"),
    ("gpt-5.3-codex", "codex"),
])
def test_infer_runtime(api_model_id, expected):
    assert infer_runtime(api_model_id) == expected

def test_infer_runtime_unknown_raises():
    with pytest.raises(ValueError):
        infer_runtime("gemini-3.1-pro")
