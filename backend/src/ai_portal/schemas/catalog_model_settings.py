"""Structured per-model settings exposed on the catalog API (UI + callers).

Stored under ``catalog_metadata["config"]`` in the database. The API also
returns a parsed :class:`ModelSettingsPublic` as ``model_settings`` for stable
contracts without clients digging through raw metadata.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator


class ReasoningSettingsPublic(BaseModel):
    """OpenAI-style reasoning effort (o-series / compatible APIs)."""

    supported: bool = False
    efforts_available: list[str] = Field(
        default_factory=list,
        description=(
            "Subset the deployment supports, e.g. minimal, low, medium, high. "
            "Empty when ``supported`` is false."
        ),
    )
    default_effort: str | None = Field(
        default=None,
        description="Suggested default when the user does not choose an effort.",
    )

    @field_validator("efforts_available", mode="before")
    @classmethod
    def _coerce_efforts(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            raise TypeError("efforts_available must be a list")
        return [str(x) for x in v]


class FloatRangePublic(BaseModel):
    min: float
    max: float
    default: float


class IntRangePublic(BaseModel):
    min: int
    max: int
    default: int


class SamplingSettingsPublic(BaseModel):
    temperature: FloatRangePublic | None = Field(
        default=None,
        description=(
            "Null when the provider fixes temperature (e.g. some reasoning models)."
        ),
    )
    max_output_tokens: IntRangePublic = Field(
        default_factory=lambda: IntRangePublic(min=1, max=128_000, default=4096),
    )


class FeatureFlagsPublic(BaseModel):
    streaming: bool = True
    vision: bool = False
    tools: bool = True
    json_mode: bool = True


class LimitsPublic(BaseModel):
    """UI / client bounds; server may enforce separately."""

    max_input_chars: int = Field(
        ge=1024,
        le=2_000_000,
        description=(
            "Suggested maximum characters for a single user message in the composer. "
            "Defaults scale with ``max_output_tokens.max`` when not set in catalog config."
        ),
    )


class ModelSettingsPublic(BaseModel):
    """Full runtime-oriented catalog entry for one chat model."""

    reasoning: ReasoningSettingsPublic = Field(default_factory=ReasoningSettingsPublic)
    sampling: SamplingSettingsPublic = Field(default_factory=SamplingSettingsPublic)
    features: FeatureFlagsPublic = Field(default_factory=FeatureFlagsPublic)
    limits: LimitsPublic = Field(
        default_factory=lambda: LimitsPublic(max_input_chars=1_048_576),
    )


def _default_sampling_chat() -> SamplingSettingsPublic:
    return SamplingSettingsPublic(
        temperature=FloatRangePublic(min=0.0, max=2.0, default=0.7),
        max_output_tokens=IntRangePublic(min=1, max=128_000, default=4096),
    )


def _derive_max_input_chars(max_output_cap: int) -> int:
    """Rough composer bound from advertised output cap (chars ≈ tokens × factor)."""
    return min(1_048_576, max(32_768, max_output_cap * 16))


def model_settings_from_metadata(
    metadata: dict[str, Any] | None,
) -> ModelSettingsPublic:
    """Parse ``metadata['config']`` with defaults for any omitted subtree."""
    meta = metadata or {}
    raw_cfg = meta.get("config")
    cfg: dict[str, Any] = raw_cfg if isinstance(raw_cfg, dict) else {}

    try:
        reasoning = ReasoningSettingsPublic.model_validate(cfg.get("reasoning") or {})

        if "sampling" in cfg and isinstance(cfg["sampling"], dict):
            sampling = SamplingSettingsPublic.model_validate(cfg["sampling"])
        else:
            sampling = _default_sampling_chat()

        features = FeatureFlagsPublic.model_validate(cfg.get("features") or {})

        limits_raw = cfg.get("limits")
        limits_dict = limits_raw if isinstance(limits_raw, dict) else {}
        derived = _derive_max_input_chars(sampling.max_output_tokens.max)
        raw_mi = limits_dict.get("max_input_chars")
        if isinstance(raw_mi, int) and raw_mi >= 1024:
            max_input_chars = min(2_000_000, raw_mi)
        else:
            max_input_chars = derived
        limits = LimitsPublic(max_input_chars=max_input_chars)

        return ModelSettingsPublic(
            reasoning=reasoning,
            sampling=sampling,
            features=features,
            limits=limits,
        )
    except ValidationError:
        return ModelSettingsPublic()
