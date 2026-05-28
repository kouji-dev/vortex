"""Tests for egress preset expansion."""

from __future__ import annotations

from ai_portal.workers.egress.presets import PRESETS, expand_presets
from ai_portal.workers.egress.policy import EgressPolicy


def test_known_presets_exist() -> None:
    for name in ("npm", "pypi", "crates", "gomod", "github", "docker"):
        assert name in PRESETS
        assert PRESETS[name], f"{name} preset should not be empty"


def test_expand_combines_presets_and_extras() -> None:
    out = expand_presets(["pypi"], extra=["custom.example.com"])
    assert "pypi.org" in out
    assert "custom.example.com" in out


def test_expand_deduplicates() -> None:
    out = expand_presets(["pypi", "pypi"], extra=["pypi.org"])
    assert out.count("pypi.org") == 1


def test_unknown_preset_silently_dropped() -> None:
    out = expand_presets(["nope"], extra=["x.com"])
    assert out == ("x.com",)


def test_expanded_presets_build_working_policy() -> None:
    patterns = expand_presets(["pypi"])
    p = EgressPolicy.from_list(patterns)
    assert p.check("pypi.org").allowed
    assert p.check("files.pythonhosted.org").allowed
    assert not p.check("evil.io").allowed
