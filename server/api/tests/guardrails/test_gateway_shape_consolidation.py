"""Consolidation — gateway-shape guardrails moved to top-level package.

Verifies the new canonical location works AND the old gateway path still
re-exports the same objects (backward compat).
"""

from __future__ import annotations


def test_protocol_canonical_import():
    from ai_portal.guardrails.gateway_shape import (
        Action,
        Guardrail,
        Hit,
        Verdict,
        clean,
    )

    v = clean()
    assert isinstance(v, Verdict)
    assert v.flagged is False
    assert v.action == "allow"
    # Action literal accepts allow/redact/block.
    _: Action = "block"
    assert Hit is not None
    assert Guardrail is not None


def test_protocol_legacy_gateway_import_re_exports_same_objects():
    from ai_portal.gateway.guardrails import Hit as GwHit
    from ai_portal.gateway.guardrails import Verdict as GwVerdict
    from ai_portal.guardrails.gateway_shape import Hit as TopHit
    from ai_portal.guardrails.gateway_shape import Verdict as TopVerdict

    # Re-exports must be the exact same classes — no shadow duplicates.
    assert GwVerdict is TopVerdict
    assert GwHit is TopHit


def test_providers_canonical_import():
    from ai_portal.guardrails.gateway_shape.providers import (
        LlamaGuardGuardrail,
        OpenAIModerationGuardrail,
        PromptInjectionGuardrail,
    )

    assert OpenAIModerationGuardrail.name == "openai_moderation"
    assert LlamaGuardGuardrail.name == "llamaguard"
    assert PromptInjectionGuardrail.name == "prompt_injection"


def test_providers_legacy_gateway_import_re_exports_same_classes():
    from ai_portal.gateway.guardrails.providers.llamaguard import (
        LlamaGuardGuardrail as GwLG,
    )
    from ai_portal.gateway.guardrails.providers.openai_moderation import (
        OpenAIModerationGuardrail as GwOM,
    )
    from ai_portal.gateway.guardrails.providers.prompt_injection import (
        PromptInjectionGuardrail as GwPI,
    )
    from ai_portal.guardrails.gateway_shape.providers.llamaguard import (
        LlamaGuardGuardrail as TopLG,
    )
    from ai_portal.guardrails.gateway_shape.providers.openai_moderation import (
        OpenAIModerationGuardrail as TopOM,
    )
    from ai_portal.guardrails.gateway_shape.providers.prompt_injection import (
        PromptInjectionGuardrail as TopPI,
    )

    assert GwLG is TopLG
    assert GwOM is TopOM
    assert GwPI is TopPI
