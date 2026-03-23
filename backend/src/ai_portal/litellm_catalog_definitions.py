"""Single source of truth: portal catalog slugs ↔ LiteLLM ``model`` strings.

LiteLLM validates ids via ``get_model_info`` against ``litellm.model_cost``. Some
OpenAI API names are accepted at runtime before they appear in that table; those
are listed in ``OPTIONAL_LITELLM_MODEL_IDS`` (see ``validate_catalog_litellm_model_id``).

Anthropic Claude ids are stored **without** the ``anthropic/`` prefix; the chat
provider adds it for completion (see ``litellm_chat.normalize_litellm_model_id_for_completion``).

**Product name → LiteLLM / API id (this repo)**

- Claude Haiku 4.5 (fast / lowest API cost) → ``claude-haiku-4-5-20251001``
  (alias ``claude-haiku-4-5``)
- Claude Sonnet 4.5 (balanced) → ``claude-sonnet-4-5-20250929``
  (alias ``claude-sonnet-4-5``)
- Claude Sonnet 4.6 (balanced) → ``claude-sonnet-4-6``
- Claude Opus 4.5 → ``claude-opus-4-5-20251101``
- Claude Opus 4.6 → ``claude-opus-4-6`` (Anthropic API alias; dated snapshots may 404)
- Claude Opus 4.6 (1M, request access) → same id; entitlement differs in the portal
- OpenAI o3-mini → ``o3-mini``
- GPT-4.5 (preview) → ``gpt-4.5-preview`` (optional registry until LiteLLM lists it)
- GPT-5.3 chat → ``gpt-5.3-chat-latest``
- GPT-5.4 chat → ``gpt-5.4`` (no separate ``gpt-5.4-chat`` in LiteLLM yet)
- GPT-5.3 Codex → ``gpt-5.3-codex``; fast → ``gpt-5.2-codex``; low → ``gpt-5.1-codex-mini``
- GPT-5.4 Codex / fast / low → ``gpt-5.4-codex*`` (optional registry; upgrade LiteLLM when shipped)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Provider = Literal["openai", "anthropic", "azure_openai"]


@dataclass(frozen=True, slots=True)
class CatalogModelDefinition:
    """One row in ``catalog_models`` (seeded by ``seed_catalog_models``)."""

    slug: str
    display_name: str
    description: str
    litellm_model_id: str
    effort: Literal["default", "low", "medium", "high"]
    sort_order: int
    requires_entitlement: bool
    request_access_url: str | None
    provider: Provider
    config_slug: str
    # When True, skip ``litellm.get_model_info`` (id not yet in LiteLLM registry).
    litellm_registry_optional: bool = False


# Slugs superseded by this seed; marked inactive so old DB rows do not duplicate the UI.
LEGACY_CATALOG_SLUGS_TO_DEACTIVATE: frozenset[str] = frozenset(
    {
        "gpt-4o-mini",
        "openai-gpt-4o",
        "openai-gpt-4-turbo",
        "openai-gpt-35-turbo",
        "azure-gpt-4o-mini",
        "azure-gpt-4o",
        "azure-gpt-4-turbo",
        "azure-gpt-35-turbo",
        "anthropic-claude-3-5-haiku",
        "anthropic-claude-3-5-sonnet",
        "anthropic-claude-3-opus",
        "anthropic-claude-3-7-sonnet",
    },
)

_REQUEST_ACCESS = "https://example.com/request-model-access"

CATALOG_MODEL_DEFINITIONS: tuple[CatalogModelDefinition, ...] = (
    # --- Anthropic (API ids; LiteLLM adds anthropic/ at completion time) ---
    CatalogModelDefinition(
        slug="anthropic-claude-haiku-4-5",
        display_name="Claude Haiku 4.5",
        description=(
            "Anthropic Haiku 4.5 — cheapest current Claude API tier; fast responses. "
            "LiteLLM / API id ``claude-haiku-4-5-20251001`` "
            "(alias ``claude-haiku-4-5``); 200k context per Anthropic docs."
        ),
        litellm_model_id="claude-haiku-4-5-20251001",
        effort="low",
        sort_order=5,
        requires_entitlement=False,
        request_access_url=None,
        provider="anthropic",
        config_slug="anthropic-claude-haiku-4-5",
    ),
    CatalogModelDefinition(
        slug="anthropic-claude-sonnet-4-5",
        display_name="Claude Sonnet 4.5",
        description=(
            "Anthropic Sonnet 4.5 — prior Sonnet generation; balanced cost vs Opus. "
            "API id ``claude-sonnet-4-5-20250929`` (alias ``claude-sonnet-4-5``)."
        ),
        litellm_model_id="claude-sonnet-4-5-20250929",
        effort="medium",
        sort_order=6,
        requires_entitlement=False,
        request_access_url=None,
        provider="anthropic",
        config_slug="anthropic-claude-sonnet-4-5",
    ),
    CatalogModelDefinition(
        slug="anthropic-claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6",
        description=(
            "Anthropic Sonnet 4.6 — balanced speed and quality; cheaper than Opus. "
            "API / LiteLLM id ``claude-sonnet-4-6``."
        ),
        litellm_model_id="claude-sonnet-4-6",
        effort="medium",
        sort_order=7,
        requires_entitlement=False,
        request_access_url=None,
        provider="anthropic",
        config_slug="anthropic-claude-sonnet-4-6",
    ),
    CatalogModelDefinition(
        slug="anthropic-claude-opus-4-5",
        display_name="Claude Opus 4.5",
        description=(
            "Anthropic Opus 4.5. LiteLLM / API id ``claude-opus-4-5-20251101`` "
            "(alias ``claude-opus-4-5``)."
        ),
        litellm_model_id="claude-opus-4-5-20251101",
        effort="high",
        sort_order=10,
        requires_entitlement=False,
        request_access_url=None,
        provider="anthropic",
        config_slug="anthropic-claude-opus-4-5",
    ),
    CatalogModelDefinition(
        slug="anthropic-claude-opus-4-6",
        display_name="Claude Opus 4.6",
        description=(
            "Anthropic Opus 4.6. API / LiteLLM id ``claude-opus-4-6`` "
            "(Anthropic rejects some dated snapshot strings at runtime)."
        ),
        litellm_model_id="claude-opus-4-6",
        effort="high",
        sort_order=20,
        requires_entitlement=False,
        request_access_url=None,
        provider="anthropic",
        config_slug="anthropic-claude-opus-4-6",
    ),
    CatalogModelDefinition(
        slug="anthropic-claude-opus-4-6-1m",
        display_name="Claude Opus 4.6 (1M context)",
        description=(
            "Same Anthropic model family as Opus 4.6 with extended 1M-token context "
            "where your org is entitled. Uses API id ``claude-opus-4-6``; "
            "enablement is on Anthropic / your account."
        ),
        litellm_model_id="claude-opus-4-6",
        effort="high",
        sort_order=30,
        requires_entitlement=True,
        request_access_url=_REQUEST_ACCESS,
        provider="anthropic",
        config_slug="anthropic-claude-opus-4-6-1m",
    ),
    # --- OpenAI (direct API via LiteLLM) ---
    CatalogModelDefinition(
        slug="openai-o3-mini",
        display_name="OpenAI o3-mini",
        description="OpenAI reasoning model. LiteLLM id ``o3-mini``.",
        litellm_model_id="o3-mini",
        effort="medium",
        sort_order=40,
        requires_entitlement=False,
        request_access_url=None,
        provider="openai",
        config_slug="openai-o3-mini",
    ),
    CatalogModelDefinition(
        slug="openai-gpt-4-5-preview",
        display_name="GPT-4.5 (preview)",
        description=(
            "OpenAI GPT-4.5 preview. LiteLLM id ``gpt-4.5-preview`` "
            "(may require a newer ``litellm`` before ``get_model_info`` recognizes it)."
        ),
        litellm_model_id="gpt-4.5-preview",
        effort="high",
        sort_order=50,
        requires_entitlement=False,
        request_access_url=None,
        provider="openai",
        config_slug="openai-gpt-4-5-preview",
        litellm_registry_optional=True,
    ),
    CatalogModelDefinition(
        slug="openai-gpt-5-3-chat-latest",
        display_name="GPT-5.3 chat",
        description="OpenAI GPT-5.3 chat. LiteLLM id ``gpt-5.3-chat-latest``.",
        litellm_model_id="gpt-5.3-chat-latest",
        effort="default",
        sort_order=60,
        requires_entitlement=False,
        request_access_url=None,
        provider="openai",
        config_slug="openai-gpt-5-3-chat-latest",
    ),
    CatalogModelDefinition(
        slug="openai-gpt-5-4",
        display_name="GPT-5.4 (chat)",
        description=(
            "OpenAI GPT-5.4 (general chat route). LiteLLM id ``gpt-5.4`` — "
            "there is no separate ``gpt-5.4-chat`` entry in LiteLLM yet."
        ),
        litellm_model_id="gpt-5.4",
        effort="default",
        sort_order=70,
        requires_entitlement=False,
        request_access_url=None,
        provider="openai",
        config_slug="openai-gpt-5-4",
    ),
    CatalogModelDefinition(
        slug="openai-gpt-5-3-codex",
        display_name="GPT-5.3 Codex",
        description="OpenAI Codex class, GPT-5.3. LiteLLM id ``gpt-5.3-codex``.",
        litellm_model_id="gpt-5.3-codex",
        effort="high",
        sort_order=80,
        requires_entitlement=True,
        request_access_url=_REQUEST_ACCESS,
        provider="openai",
        config_slug="openai-gpt-5-3-codex",
    ),
    CatalogModelDefinition(
        slug="openai-gpt-5-3-codex-fast",
        display_name="GPT-5.3 Codex (fast)",
        description=(
            "Faster Codex-tier route in the GPT-5.x family. LiteLLM id ``gpt-5.2-codex`` "
            "(closest registered “fast” codex sibling to 5.3)."
        ),
        litellm_model_id="gpt-5.2-codex",
        effort="medium",
        sort_order=90,
        requires_entitlement=True,
        request_access_url=_REQUEST_ACCESS,
        provider="openai",
        config_slug="openai-gpt-5-3-codex-fast",
    ),
    CatalogModelDefinition(
        slug="openai-gpt-5-3-codex-low",
        display_name="GPT-5.3 Codex (low)",
        description=(
            "Lighter Codex / coding tier. LiteLLM id ``gpt-5.1-codex-mini`` "
            "(closest registered “low” codex sibling in LiteLLM today)."
        ),
        litellm_model_id="gpt-5.1-codex-mini",
        effort="low",
        sort_order=100,
        requires_entitlement=True,
        request_access_url=_REQUEST_ACCESS,
        provider="openai",
        config_slug="openai-gpt-5-3-codex-low",
    ),
    CatalogModelDefinition(
        slug="openai-gpt-5-4-codex",
        display_name="GPT-5.4 Codex",
        description=(
            "OpenAI GPT-5.4 Codex (request access). Proposed LiteLLM id ``gpt-5.4-codex`` — "
            "not yet in ``model_cost``; upgrade litellm when available."
        ),
        litellm_model_id="gpt-5.4-codex",
        effort="high",
        sort_order=110,
        requires_entitlement=True,
        request_access_url=_REQUEST_ACCESS,
        provider="openai",
        config_slug="openai-gpt-5-4-codex",
        litellm_registry_optional=True,
    ),
    CatalogModelDefinition(
        slug="openai-gpt-5-4-codex-fast",
        display_name="GPT-5.4 Codex (fast)",
        description="Proposed id ``gpt-5.4-codex-fast`` (request access).",
        litellm_model_id="gpt-5.4-codex-fast",
        effort="medium",
        sort_order=120,
        requires_entitlement=True,
        request_access_url=_REQUEST_ACCESS,
        provider="openai",
        config_slug="openai-gpt-5-4-codex-fast",
        litellm_registry_optional=True,
    ),
    CatalogModelDefinition(
        slug="openai-gpt-5-4-codex-low",
        display_name="GPT-5.4 Codex (low)",
        description="Proposed id ``gpt-5.4-codex-low`` (request access).",
        litellm_model_id="gpt-5.4-codex-low",
        effort="low",
        sort_order=130,
        requires_entitlement=True,
        request_access_url=_REQUEST_ACCESS,
        provider="openai",
        config_slug="openai-gpt-5-4-codex-low",
        litellm_registry_optional=True,
    ),
)

# Ids accepted in catalog before LiteLLM lists them in ``model_cost``.
OPTIONAL_LITELLM_MODEL_IDS: frozenset[str] = frozenset(
    d.litellm_model_id for d in CATALOG_MODEL_DEFINITIONS if d.litellm_registry_optional
)


def definition_by_slug() -> dict[str, CatalogModelDefinition]:
    return {d.slug: d for d in CATALOG_MODEL_DEFINITIONS}
