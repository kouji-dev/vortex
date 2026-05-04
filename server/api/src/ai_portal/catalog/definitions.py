"""Single source of truth: portal catalog slugs ↔ vendor API model ids.

Runtime chat uses LangChain ``ChatAnthropic`` / ``ChatOpenAI`` with these strings.

Ids in ``OPTIONAL_CATALOG_API_MODEL_IDS`` skip strict catalog seed checks
(preview / not-yet-stable names).

Anthropic Claude ids are stored **without** the ``anthropic/`` prefix.

**Product name → API id (this repo)**

- Claude Haiku 4.5 (fast / lowest API cost) → ``claude-haiku-4-5-20251001``
  (alias ``claude-haiku-4-5``)
- Claude Sonnet 4.5 (balanced) → ``claude-sonnet-4-5-20250929``
  (alias ``claude-sonnet-4-5``)
- Claude Sonnet 4.6 (balanced) → ``claude-sonnet-4-6``
- Claude Opus 4.5 → ``claude-opus-4-5-20251101``
- Claude Opus 4.6 → ``claude-opus-4-6`` (Anthropic API alias; dated snapshots may 404)
- Claude Opus 4.6 (1M, request access) → same id; entitlement differs in the portal
- OpenAI o3-mini → ``o3-mini``
- GPT-4.5 (preview) → ``gpt-4.5-preview`` (optional until provider availability is confirmed)
- GPT-5.3 chat → ``gpt-5.3-chat-latest``
- GPT-5.4 chat → ``gpt-5.4``
- GPT-5.3 Codex → ``gpt-5.3-codex``; fast → ``gpt-5.2-codex``; low → ``gpt-5.1-codex-mini``
- GPT-5.4 Codex / fast / low → ``gpt-5.4-codex*`` (optional / preview)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Provider = Literal["openai", "anthropic", "azure_openai", "google"]


@dataclass(frozen=True, slots=True)
class CatalogModelDefinition:
    """One row in ``catalog_models`` (seeded by ``seed_catalog_models``)."""

    slug: str
    display_name: str
    description: str
    api_model_id: str
    effort: Literal["default", "low", "medium", "high"]
    sort_order: int
    requires_entitlement: bool
    request_access_url: str | None
    provider: Provider
    config_slug: str
    # When True, skip strict catalog seed checks for this id (preview / uncertain availability).
    catalog_validation_optional: bool = False


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
    # --- Anthropic (API ids; LangChain ChatAnthropic uses bare claude-* ids) ---
    CatalogModelDefinition(
        slug="anthropic-claude-haiku-4-5",
        display_name="Claude Haiku 4.5",
        description=(
            "Anthropic Haiku 4.5 — cheapest current Claude API tier; fast responses. "
            "API id ``claude-haiku-4-5-20251001`` "
            "(alias ``claude-haiku-4-5``); 200k context per Anthropic docs."
        ),
        api_model_id="claude-haiku-4-5-20251001",
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
        api_model_id="claude-sonnet-4-5-20250929",
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
            "API id ``claude-sonnet-4-6``."
        ),
        api_model_id="claude-sonnet-4-6",
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
            "Anthropic Opus 4.5. API id ``claude-opus-4-5-20251101`` "
            "(alias ``claude-opus-4-5``)."
        ),
        api_model_id="claude-opus-4-5-20251101",
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
            "Anthropic Opus 4.6. API id ``claude-opus-4-6`` "
            "(Anthropic rejects some dated snapshot strings at runtime)."
        ),
        api_model_id="claude-opus-4-6",
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
        api_model_id="claude-opus-4-6",
        effort="high",
        sort_order=30,
        requires_entitlement=True,
        request_access_url=_REQUEST_ACCESS,
        provider="anthropic",
        config_slug="anthropic-claude-opus-4-6-1m",
    ),
    CatalogModelDefinition(
        slug="anthropic-claude-opus-4-7",
        display_name="Claude Opus 4.7",
        description=(
            "Anthropic Opus 4.7 — most capable Claude model with extended thinking. "
            "API id ``claude-opus-4-7``."
        ),
        api_model_id="claude-opus-4-7",
        effort="high",
        sort_order=35,
        requires_entitlement=False,
        request_access_url=None,
        provider="anthropic",
        config_slug="anthropic-claude-opus-4-7",
        catalog_validation_optional=True,
    ),
    # --- OpenAI (direct API via LangChain ChatOpenAI) ---
    CatalogModelDefinition(
        slug="openai-o3-mini",
        display_name="OpenAI o3-mini",
        description="OpenAI reasoning model. API id ``o3-mini``.",
        api_model_id="o3-mini",
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
            "OpenAI GPT-4.5 preview. API id ``gpt-4.5-preview`` "
            "(availability may vary by account / region)."
        ),
        api_model_id="gpt-4.5-preview",
        effort="high",
        sort_order=50,
        requires_entitlement=False,
        request_access_url=None,
        provider="openai",
        config_slug="openai-gpt-4-5-preview",
        catalog_validation_optional=True,
    ),
    CatalogModelDefinition(
        slug="openai-gpt-5-3-chat-latest",
        display_name="GPT-5.3 chat",
        description="OpenAI GPT-5.3 chat. API id ``gpt-5.3-chat-latest``.",
        api_model_id="gpt-5.3-chat-latest",
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
            "OpenAI GPT-5.4 (general chat route). API id ``gpt-5.4``."
        ),
        api_model_id="gpt-5.4",
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
        description="OpenAI Codex class, GPT-5.3. API id ``gpt-5.3-codex``.",
        api_model_id="gpt-5.3-codex",
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
            "Faster Codex-tier route in the GPT-5.x family. API id ``gpt-5.2-codex``."
        ),
        api_model_id="gpt-5.2-codex",
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
            "Lighter Codex / coding tier. API id ``gpt-5.1-codex-mini``."
        ),
        api_model_id="gpt-5.1-codex-mini",
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
            "OpenAI GPT-5.4 Codex (request access). API id ``gpt-5.4-codex`` "
            "(preview; confirm availability before enabling in production)."
        ),
        api_model_id="gpt-5.4-codex",
        effort="high",
        sort_order=110,
        requires_entitlement=True,
        request_access_url=_REQUEST_ACCESS,
        provider="openai",
        config_slug="openai-gpt-5-4-codex",
        catalog_validation_optional=True,
    ),
    CatalogModelDefinition(
        slug="openai-gpt-5-4-codex-fast",
        display_name="GPT-5.4 Codex (fast)",
        description="Proposed id ``gpt-5.4-codex-fast`` (request access).",
        api_model_id="gpt-5.4-codex-fast",
        effort="medium",
        sort_order=120,
        requires_entitlement=True,
        request_access_url=_REQUEST_ACCESS,
        provider="openai",
        config_slug="openai-gpt-5-4-codex-fast",
        catalog_validation_optional=True,
    ),
    CatalogModelDefinition(
        slug="openai-gpt-5-4-codex-low",
        display_name="GPT-5.4 Codex (low)",
        description="Proposed id ``gpt-5.4-codex-low`` (request access).",
        api_model_id="gpt-5.4-codex-low",
        effort="low",
        sort_order=130,
        requires_entitlement=True,
        request_access_url=_REQUEST_ACCESS,
        provider="openai",
        config_slug="openai-gpt-5-4-codex-low",
        catalog_validation_optional=True,
    ),
    # --- Google Gemini (via LangChain ChatGoogleGenerativeAI) ---
    CatalogModelDefinition(
        slug="google-gemini-2-5-flash-lite",
        display_name="Gemini 2.5 Flash Lite",
        description=(
            "Google Gemini 2.5 Flash Lite — cheapest Gemini tier; fast, high-throughput. "
            "API id ``gemini-2.5-flash-lite``."
        ),
        api_model_id="gemini-2.5-flash-lite",
        effort="low",
        sort_order=200,
        requires_entitlement=False,
        request_access_url=None,
        provider="google",
        config_slug="google-gemini-2-5-flash-lite",
    ),
    CatalogModelDefinition(
        slug="google-gemini-2-5-flash",
        display_name="Gemini 2.5 Flash",
        description=(
            "Google Gemini 2.5 Flash — fast, cost-efficient multimodal model. "
            "API id ``gemini-2.5-flash``."
        ),
        api_model_id="gemini-2.5-flash",
        effort="low",
        sort_order=210,
        requires_entitlement=False,
        request_access_url=None,
        provider="google",
        config_slug="google-gemini-2-5-flash",
    ),
    CatalogModelDefinition(
        slug="google-gemini-2-5-pro",
        display_name="Gemini 2.5 Pro",
        description=(
            "Google Gemini 2.5 Pro — advanced reasoning and coding. "
            "API id ``gemini-2.5-pro``."
        ),
        api_model_id="gemini-2.5-pro",
        effort="high",
        sort_order=220,
        requires_entitlement=False,
        request_access_url=None,
        provider="google",
        config_slug="google-gemini-2-5-pro",
    ),
    CatalogModelDefinition(
        slug="google-gemini-3-flash",
        display_name="Gemini 3 Flash",
        description=(
            "Google Gemini 3 Flash — next-gen fast model. "
            "API id ``gemini-3-flash``."
        ),
        api_model_id="gemini-3-flash",
        effort="low",
        sort_order=230,
        requires_entitlement=False,
        request_access_url=None,
        provider="google",
        config_slug="google-gemini-3-flash",
        catalog_validation_optional=True,
    ),
    CatalogModelDefinition(
        slug="google-gemini-3-1-flash-lite",
        display_name="Gemini 3.1 Flash Lite",
        description=(
            "Google Gemini 3.1 Flash Lite — cheapest 3.x tier. "
            "API id ``gemini-3.1-flash-lite``."
        ),
        api_model_id="gemini-3.1-flash-lite",
        effort="low",
        sort_order=240,
        requires_entitlement=False,
        request_access_url=None,
        provider="google",
        config_slug="google-gemini-3-1-flash-lite",
        catalog_validation_optional=True,
    ),
    CatalogModelDefinition(
        slug="google-gemini-3-1-flash-lite-preview",
        display_name="Gemini 3.1 Flash Lite (preview)",
        description=(
            "Google Gemini 3.1 Flash Lite preview. "
            "API id ``gemini-3.1-flash-lite-preview``."
        ),
        api_model_id="gemini-3.1-flash-lite-preview",
        effort="low",
        sort_order=250,
        requires_entitlement=False,
        request_access_url=None,
        provider="google",
        config_slug="google-gemini-3-1-flash-lite-preview",
        catalog_validation_optional=True,
    ),
    CatalogModelDefinition(
        slug="google-gemini-3-1-pro",
        display_name="Gemini 3.1 Pro",
        description=(
            "Google Gemini 3.1 Pro — high-capability reasoning model. "
            "API id ``gemini-3.1-pro``."
        ),
        api_model_id="gemini-3.1-pro",
        effort="high",
        sort_order=260,
        requires_entitlement=False,
        request_access_url=None,
        provider="google",
        config_slug="google-gemini-3-1-pro",
        catalog_validation_optional=True,
    ),
    CatalogModelDefinition(
        slug="google-gemini-3-1-pro-preview",
        display_name="Gemini 3.1 Pro (preview)",
        description=(
            "Google Gemini 3.1 Pro preview. "
            "API id ``gemini-3.1-pro-preview``."
        ),
        api_model_id="gemini-3.1-pro-preview",
        effort="high",
        sort_order=270,
        requires_entitlement=False,
        request_access_url=None,
        provider="google",
        config_slug="google-gemini-3-1-pro-preview",
        catalog_validation_optional=True,
    ),
)

# Ids accepted in catalog before strict validation lists them.
OPTIONAL_CATALOG_API_MODEL_IDS: frozenset[str] = frozenset(
    d.api_model_id for d in CATALOG_MODEL_DEFINITIONS if d.catalog_validation_optional
)


def definition_by_slug() -> dict[str, CatalogModelDefinition]:
    return {d.slug: d for d in CATALOG_MODEL_DEFINITIONS}
