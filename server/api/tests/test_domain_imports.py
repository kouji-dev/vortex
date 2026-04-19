"""Smoke test: verify all domain packages export their public API correctly."""
import pytest


def test_core_config_imports():
    from ai_portal.core.config import get_settings, Settings, settings_log_snapshot
    assert callable(get_settings)


def test_core_db_imports():
    from ai_portal.core.db.session import SessionLocal, engine
    from ai_portal.core.db.base import Base
    from ai_portal.core.db.types import ConversationSettingsJSON
    assert SessionLocal is not None


def test_core_middleware_imports():
    from ai_portal.core.middleware.setup_guard import SetupGuardMiddleware
    assert SetupGuardMiddleware is not None


def test_rag_imports():
    from ai_portal.rag.protocols import EmbeddingProvider
    from ai_portal.rag.providers.voyage import embed_texts, embeddings_configured
    from ai_portal.rag.service import retrieve_context_with_meta
    assert callable(retrieve_context_with_meta)


def test_catalog_imports():
    from ai_portal.catalog.definitions import OPTIONAL_CATALOG_API_MODEL_IDS
    from ai_portal.catalog.repository import (
        get_active_catalog_model_by_slug,
        get_active_catalog_models_by_api_model_id,
        get_all_active_catalog_models,
    )
    from ai_portal.catalog.service import (
        effective_chat_model,
        validate_catalog_model_id,
        resolve_stored_model_to_chat_model,
        resolve_default_conversation_api_model,
        resolve_default_conversation_stored_model,
        default_conversation_settings,
    )
    from ai_portal.catalog.providers.protocol import ChatProvider
    from ai_portal.catalog.providers.routing import (
        normalize_openai_compatible_base,
        remap_deprecated_chat_model,
        normalize_model_id_for_langchain_chat,
        is_langchain_anthropic_model,
        chat_provider_credential_kwargs,
    )
    assert callable(effective_chat_model)


def test_auth_imports():
    from ai_portal.auth.deps import get_db, get_current_user, get_app_roles, get_current_org_id
    from ai_portal.auth.service import profile_fields_from_claims, upsert_user_from_entra_claims
    from ai_portal.auth.strategies.entra import decode_entra_access_token, roles_from_claims
    from ai_portal.auth.strategies.jwt import decode_token
    from ai_portal.auth.strategies.dev import UserManager, AuthenticationError, RegistrationError
    from ai_portal.auth.strategies.portal_keys import (
        hash_portal_api_key, create_portal_api_key, user_for_portal_api_key,
        list_keys_for_user, revoke_key,
    )
    from ai_portal.auth.schemas import (
        RegisterRequest, LoginRequest, RefreshRequest,
        TokenResponse, UserRead, AcceptInviteRequest,
    )
    assert callable(get_current_user)


def test_knowledge_base_imports():
    from ai_portal.knowledge_base.router import router
    from ai_portal.knowledge_base.ingest_service import (
        ingest_uses_queue, enqueue_document_ingest,
        INGEST_QUEUE_NAME, INGEST_JOB_FUNC,
    )
    from ai_portal.knowledge_base.workers.ingest.worker import ingest_document_worker
    from ai_portal.knowledge_base.workers.ingest.job import run_ingest_job
    assert INGEST_JOB_FUNC == "ai_portal.knowledge_base.workers.ingest.job.run_ingest_job"


def test_chat_imports():
    from ai_portal.chat.router import router
    from ai_portal.chat.schemas import ConversationSettings, CapabilityToggles
    from ai_portal.memory.workers.extractor import extract_user_memories
    from ai_portal.memory.workers.summarizer import summarize_conversation
    assert ConversationSettings is not None


def test_no_legacy_paths_exist():
    """Verify legacy module paths have been removed."""
    import importlib
    legacy_paths = [
        "ai_portal.services.rag",
        "ai_portal.services.embedding",
        "ai_portal.services.ingest_queue",
        "ai_portal.services.user_identity",
        "ai_portal.services.portal_api_keys",
        "ai_portal.services.model_access",
        "ai_portal.services.llm",
        "ai_portal.services.llm_connect",
        "ai_portal.workers.ingest.worker",
        "ai_portal.workers.memory.extractor",
        "ai_portal.logging_config",
        "ai_portal.catalog_model_definitions",
        "ai_portal.catalog_specs",
    ]
    for path in legacy_paths:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(path)
