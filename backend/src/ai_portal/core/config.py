import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import AliasChoices, Field, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


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


# Maps YAML nested path → flat Settings field name.
# Format: "section.yaml_key": "settings_field_name"
_YAML_KEY_MAP: dict[str, str] = {
    "server.host": "api_host",
    "server.port": "api_port",
    "server.cors_origins": "cors_origins",
    "server.upload_dir": "upload_dir",
    "server.deployment_mode": "deployment_mode",
    "database.url": "database_url",
    "auth.mode": "auth_mode",
    "auth.secret_key": "secret_key",
    "auth.dev_bearer_token": "dev_bearer_token",
    "auth.dev_seed_user_email": "dev_seed_user_email",
    "auth.portal_api_key_pepper": "portal_api_key_pepper",
    "auth.entra_tenant_id": "entra_tenant_id",
    "auth.entra_api_audience": "entra_api_audience",
    "auth.entra_debug_jwt": "entra_debug_jwt",
    "smtp.host": "smtp_host",
    "smtp.port": "smtp_port",
    "smtp.user": "smtp_user",
    "smtp.password": "smtp_password",
    "smtp.email_from": "email_from",
    "llm.openai_api_base": "openai_api_base",
    "llm.openai_api_key": "openai_api_key",
    "llm.anthropic_api_key": "anthropic_api_key",
    "llm.gemini_api_key": "gemini_api_key",
    "llm.chat_default_api_model": "chat_default_api_model",
    "llm.default_system_prompt": "default_system_prompt",
    "embedding.voyage_api_key": "voyage_api_key",
    "embedding.model": "embedding_model",
    "ingest.max_file_size_mb": "kb_max_file_size_mb",
    "ingest.commit_batch_size": "ingest_commit_batch_size",
    "ingest.embed_batch_size": "ingest_embed_batch_size",
    "rag.max_top_k": "rag_max_top_k",
    "rag.min_top_k": "rag_min_top_k",
    "rag.similarity_threshold": "rag_similarity_threshold",
    "rag.max_tool_iterations": "rag_max_tool_iterations",
    "conversation.base_window_size": "conversation_base_window_size",
    "conversation.summary_interval": "conversation_summary_interval",
    "conversation.inactivity_summary_hours": "conversation_inactivity_summary_hours",
    "observability.langfuse_public_key": "langfuse_public_key",
    "observability.langfuse_secret_key": "langfuse_secret_key",
    "observability.langfuse_host": "langfuse_host",
}


def _default_config_path() -> Path:
    """Return path to config.yaml next to pyproject.toml (i.e. backend/config.yaml)."""
    return Path(__file__).parent.parent.parent.parent / "config.yaml"


class YamlSettingsSource(PydanticBaseSettingsSource):
    """Loads settings from a structured config.yaml, flattening nested sections."""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        env_path = os.environ.get("AI_PORTAL_CONFIG")
        self._path = Path(env_path) if env_path else _default_config_path()

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as fh:
            try:
                data = yaml.safe_load(fh) or {}
            except yaml.YAMLError as exc:
                raise ValueError(f"Invalid YAML in {self._path}: {exc}") from exc
        flat: dict[str, Any] = {}
        for section, values in data.items():
            if not isinstance(values, dict):
                continue
            for key, value in values.items():
                yaml_path = f"{section}.{key}"
                field_name = _YAML_KEY_MAP.get(yaml_path)
                if field_name is not None:
                    flat[field_name] = value
        return flat

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        # Required by PydanticBaseSettingsSource ABC.
        # Not called by pydantic-settings when __call__ is overridden,
        # but must be present to satisfy the abstract method contract.
        data = self._load()
        value = data.get(field_name)
        return value, field_name, False

    def __call__(self) -> dict[str, Any]:
        return self._load()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        populate_by_name=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (env_settings, YamlSettingsSource(settings_cls), init_settings)

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

    # New deployment mode — replaces auth_mode for new deployments.
    # dev = dev token (backward compat)
    # saas = open signup, JWT local auth
    # selfhosted = invite-only, JWT local auth, setup wizard on first boot
    deployment_mode: Literal["dev", "saas", "selfhosted"] = Field(
        default="dev",
        validation_alias=AliasChoices("DEPLOYMENT_MODE"),
    )

    # Required for local auth JWT signing.
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    secret_key: str = Field(default="", validation_alias=AliasChoices("SECRET_KEY"))

    # SMTP for email verification, password reset, and invites
    smtp_host: str = Field(default="", validation_alias=AliasChoices("SMTP_HOST"))
    smtp_port: int = Field(default=587, validation_alias=AliasChoices("SMTP_PORT"))
    smtp_user: str = Field(default="", validation_alias=AliasChoices("SMTP_USER"))
    smtp_password: str = Field(default="", validation_alias=AliasChoices("SMTP_PASSWORD"))
    email_from: str = Field(default="noreply@example.com", validation_alias=AliasChoices("EMAIL_FROM"))

    # OpenAI chat + OpenAI-compatible embeddings (direct API or compatible gateway).
    openai_api_base: str = Field(
        default="https://api.openai.com/v1",
        validation_alias="OPENAI_API_BASE",
    )
    openai_api_key: str = Field(
        default="",
        validation_alias="OPENAI_API_KEY",
    )
    # LangChain ``ChatAnthropic`` / ``claude-*`` models (separate from ``OPENAI_API_KEY``).
    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ANTHROPIC_API_KEY"),
    )
    # Google Gemini: set ``GEMINI_API_KEY``. Used for ``gemini-*`` models via
    # LangChain ``ChatGoogleGenerativeAI``.
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_API_KEY"),
    )

    # HMAC pepper for hashing portal API keys (``aip_…``). Empty = dev-only SHA-256.
    portal_api_key_pepper: str = ""

    # Voyage: set ``VOYAGE_API_KEY``. Default embedding model is ``voyage-4-lite`` (cheapest
    # current Voyage text embedding tier; see https://docs.voyageai.com/docs/pricing ).
    # OpenAI embeddings: leave ``VOYAGE_API_KEY`` unset, set ``OPENAI_API_KEY`` and e.g.
    # ``EMBEDDING_MODEL=text-embedding-3-small`` (stored as 1024-d — see Alembic 015).
    voyage_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("VOYAGE_API_KEY"),
    )
    embedding_model: str = Field(
        default="",
        validation_alias=AliasChoices("EMBEDDING_MODEL"),
    )
    # Default vendor API model id: new conversations (if no catalog default), stream
    # fallback when conversation has no model, and LangChain when no per-request model.
    # Env: ``CHAT_DEFAULT_API_MODEL`` (preferred), ``CHAT_DEFAULT_MODEL``, or legacy ``CHAT_MODEL``.
    chat_default_api_model: str = Field(
        default="gemini-2.5-flash-lite",
        validation_alias=AliasChoices(
            "CHAT_DEFAULT_API_MODEL",
            "CHAT_DEFAULT_MODEL",
            "CHAT_MODEL",
        ),
    )
    default_system_prompt: str = "You are a helpful assistant."

    upload_dir: str = "data/uploads"

    # Queue / Redis (optional; if empty, background tasks run in-process)
    redis_url: str = Field(
        default="",
        validation_alias=AliasChoices("REDIS_URL"),
    )

    # Ingest worker
    kb_max_file_size_mb: int = Field(
        default=500,
        validation_alias=AliasChoices("KB_MAX_FILE_SIZE_MB"),
    )
    ingest_commit_batch_size: int = Field(
        default=100,
        validation_alias=AliasChoices("INGEST_COMMIT_BATCH_SIZE"),
    )
    ingest_embed_batch_size: int = Field(
        default=128,
        validation_alias=AliasChoices("INGEST_EMBED_BATCH_SIZE"),
    )

    # RAG retrieval
    rag_max_top_k: int = Field(
        default=30,
        validation_alias=AliasChoices("RAG_MAX_TOP_K"),
    )
    rag_min_top_k: int = Field(
        default=8,
        validation_alias=AliasChoices("RAG_MIN_TOP_K"),
    )
    rag_similarity_threshold: float = Field(
        default=0.3,
        validation_alias=AliasChoices("RAG_SIMILARITY_THRESHOLD"),
    )
    rag_max_tool_iterations: int = Field(
        default=1,
        validation_alias=AliasChoices("RAG_MAX_TOOL_ITERATIONS"),
    )

    # Conversation memory
    conversation_base_window_size: int = Field(
        default=30,
        validation_alias=AliasChoices("CONVERSATION_BASE_WINDOW_SIZE", "CONVERSATION_WINDOW_SIZE"),
    )
    conversation_summary_interval: int = Field(
        default=10,
        validation_alias=AliasChoices("CONVERSATION_SUMMARY_INTERVAL"),
    )
    conversation_inactivity_summary_hours: int = Field(
        default=1,
        validation_alias=AliasChoices("CONVERSATION_INACTIVITY_SUMMARY_HOURS"),
    )

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _require_secret_key_in_auth_modes(self) -> "Settings":
        if self.deployment_mode in ("saas", "selfhosted") and not self.secret_key.strip():
            raise ValueError(
                "SECRET_KEY must be set when DEPLOYMENT_MODE is 'saas' or 'selfhosted'"
            )
        return self

    @model_validator(mode="after")
    def _entra_requires_portal_api_key_pepper(self) -> "Settings":
        validate_portal_api_key_pepper_for_auth_mode(
            self.auth_mode,
            self.portal_api_key_pepper,
        )
        return self


def _redact_database_url(url: str) -> str:
    """Hide credentials in SQLAlchemy-style URLs for logs."""
    if "://" not in url or "@" not in url:
        return url
    scheme, remainder = url.split("://", 1)
    if "@" not in remainder:
        return url
    creds, hostpath = remainder.split("@", 1)
    if ":" not in creds:
        return url
    user, _pwd = creds.split(":", 1)
    return f"{scheme}://{user}:***@{hostpath}"


def settings_log_snapshot(st: Settings) -> dict[str, Any]:
    """Non-secret view of settings for startup logging."""
    return {
        "auth_mode": st.auth_mode,
        "api_host": st.api_host,
        "api_port": st.api_port,
        "cors_origins": st.cors_origins,
        "database_url": _redact_database_url(st.database_url),
        "dev_seed_user_email": st.dev_seed_user_email,
        "dev_bearer_token_configured": bool(st.dev_bearer_token.strip()),
        "entra_tenant_id": st.entra_tenant_id or "(empty)",
        "entra_api_audience": st.entra_api_audience or "(empty)",
        "entra_debug_jwt": st.entra_debug_jwt,
        "openai_api_base": st.openai_api_base,
        "openai_api_key_set": bool(st.openai_api_key.strip()),
        "anthropic_api_key_set": bool(st.anthropic_api_key.strip()),
        "gemini_api_key_set": bool(st.gemini_api_key.strip()),
        "voyage_api_key_set": bool(st.voyage_api_key.strip()),
        "embedding_model": st.embedding_model or "(default)",
        "chat_default_api_model": st.chat_default_api_model,
        "upload_dir": st.upload_dir,
        "portal_api_key_pepper_set": bool(st.portal_api_key_pepper.strip()),
        "langfuse_host": st.langfuse_host,
        "langfuse_public_key_set": bool(st.langfuse_public_key.strip()),
        "langfuse_secret_key_set": bool(st.langfuse_secret_key.strip()),
        "deployment_mode": st.deployment_mode,
        "secret_key_set": bool(st.secret_key.strip()),
        "smtp_host": st.smtp_host or "(not set)",
    }


def get_settings() -> Settings:
    """Fresh ``Settings()`` each call so edits to ``.env`` apply without restarting workers.

    (``uvicorn --reload`` only watches code files, not ``.env``.)
    """
    return Settings()
