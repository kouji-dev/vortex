from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def validate_portal_api_key_pepper_for_auth_mode(
    auth_mode: Literal["dev", "entra"],
    portal_api_key_pepper: str,
) -> None:
    """Entra deployments must set a non-empty pepper so portal API keys are HMAC-hashed."""
    if auth_mode == "entra" and not portal_api_key_pepper.strip():
        msg = (
            "PORTAL_API_KEY_PEPPER is required when AUTH_MODE=entra "
            "(portal API keys use HMAC; set a long random secret in production)."
        )
        raise ValueError(msg)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5434/ai_portal"
    cors_origins: str = "http://localhost:5173"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    dev_bearer_token: str = "devtoken"
    dev_seed_user_email: str = "dev@localhost"

    auth_mode: Literal["dev", "entra"] = "dev"
    entra_tenant_id: str = ""
    entra_api_audience: str = ""
    # Local debugging only: include PyJWT error text in 401 responses for Entra tokens.
    entra_debug_jwt: bool = Field(default=False, validation_alias="ENTRA_DEBUG_JWT")

    # LiteLLM: OpenAI-compatible base URL + key (vendor, LiteLLM proxy, …).
    # ``OPENAI_*`` env vars still work as aliases.
    llm_api_base: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices("LLM_API_BASE", "OPENAI_API_BASE"),
    )
    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_API_KEY", "OPENAI_API_KEY"),
    )
    # Used for LiteLLM ``claude-*`` models (and as fallback if ``LLM_API_KEY`` is unset).
    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ANTHROPIC_API_KEY"),
    )

    # HMAC pepper for hashing portal API keys (``aip_…``). Empty = dev-only SHA-256.
    portal_api_key_pepper: str = ""

    # Embedding model id understood by LiteLLM for your chosen route.
    embedding_model: str = "text-embedding-3-small"
    chat_model: str = "o3-mini"
    # Used when ``POST /api/chat/conversations`` omits ``model`` and no preferred
    # catalog row exists in ``catalog_models``.
    chat_default_litellm_model: str = Field(
        default="claude-haiku-4-5-20251001",
        validation_alias=AliasChoices(
            "CHAT_DEFAULT_LITELLM_MODEL",
            "CHAT_DEFAULT_MODEL",
        ),
    )
    default_system_prompt: str = "You are a helpful assistant."

    upload_dir: str = "data/uploads"

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _entra_requires_portal_api_key_pepper(self) -> "Settings":
        validate_portal_api_key_pepper_for_auth_mode(
            self.auth_mode,
            self.portal_api_key_pepper,
        )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
