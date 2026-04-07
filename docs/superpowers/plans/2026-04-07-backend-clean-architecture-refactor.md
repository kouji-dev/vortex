# Backend Clean Architecture Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganise the Python backend into a domain-first, hybrid-hexagonal structure — no logic changes, only file movement and import-path updates.

**Architecture:** Each domain (`chat`, `knowledge_base`, `catalog`, `auth`, `rag`) becomes a self-contained package with `router.py / service.py / repository.py / schemas.py`. Shared infrastructure moves to `core/`. Workers move inside their owning domain under a `workers/` subfolder. Two Protocol interfaces (`LLMProvider` in `catalog/providers/`, `EmbeddingProvider` in `rag/`) guard the only volatile external boundaries.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy (sync), Pydantic v2, Alembic, pytest.

---

## Implementation Order

1. `core/` — shared infra (no domain dependencies)
2. `rag/` — no domain dependencies
3. `catalog/` — depends on `core/`
4. `auth/` — depends on `core/`
5. `knowledge_base/` — depends on `core/`, `rag/`
6. `chat/` — depends on everything (most complex, last)

> **Important:** After every task, the app must still import and start (`uvicorn ai_portal.main:app`). Use re-export shims (`from ai_portal.new.location import x`) in old locations during the migration to keep unrelated tests passing. Remove shims only in the final cleanup task.

---

## File Map

### New files (all `__init__.py` unless noted)

| New path | Source |
|---|---|
| `core/__init__.py` | new |
| `core/config.py` | `config.py` |
| `core/logging.py` | `logging_config.py` |
| `core/db/__init__.py` | `db/__init__.py` |
| `core/db/session.py` | `db/session.py` |
| `core/db/base.py` | `db/base.py` |
| `core/db/types.py` | `db/json_types.py` + `db/tenant.py` |
| `core/middleware/__init__.py` | `middleware/__init__.py` |
| `core/middleware/setup_guard.py` | `middleware/setup_guard.py` |
| `rag/__init__.py` | new |
| `rag/service.py` | `services/rag.py` |
| `rag/protocols.py` | new (EmbeddingProvider Protocol) |
| `rag/providers/__init__.py` | new |
| `rag/providers/voyage.py` | `services/embedding.py` |
| `catalog/__init__.py` | new |
| `catalog/router.py` | `api/model_catalog.py` |
| `catalog/service.py` | `services/model_access.py` + `services/catalog_model_validate.py` + `services/conversation_model_resolve.py` + `services/default_conversation_model.py` |
| `catalog/repository.py` | DB queries extracted from above services |
| `catalog/schemas.py` | schemas from `api/model_catalog.py` + `schemas/catalog_model_settings.py` |
| `catalog/definitions.py` | `catalog_model_definitions.py` |
| `catalog/specs.py` | `catalog_specs.py` |
| `catalog/providers/__init__.py` | `services/llm_providers/__init__.py` |
| `catalog/providers/protocol.py` | `services/llm_providers/protocol.py` |
| `catalog/providers/langchain.py` | `services/llm_providers/langchain_chat.py` |
| `catalog/providers/routing.py` | `services/llm_providers/model_routing.py` + `services/llm_connect.py` |
| `auth/__init__.py` | new |
| `auth/router.py` | `api/auth.py` |
| `auth/service.py` | `services/user_identity.py` |
| `auth/repository.py` | DB queries from `api/auth.py` + `api/orgs.py` |
| `auth/schemas.py` | schemas from `api/auth.py` |
| `auth/deps.py` | `api/deps.py` |
| `auth/strategies/__init__.py` | new |
| `auth/strategies/dev.py` | dev-auth slice from `api/deps.py` |
| `auth/strategies/entra.py` | `auth/entra.py` |
| `auth/strategies/jwt.py` | `auth/jwt.py` |
| `auth/strategies/portal_keys.py` | `services/portal_api_keys.py` |
| `knowledge_base/__init__.py` | new |
| `knowledge_base/router.py` | `api/knowledge_bases.py` (routes only) |
| `knowledge_base/service.py` | business logic from `api/knowledge_bases.py` + `services/ingest_queue.py` |
| `knowledge_base/repository.py` | DB queries extracted from `api/knowledge_bases.py` |
| `knowledge_base/schemas.py` | Pydantic models from `api/knowledge_bases.py` |
| `knowledge_base/workers/__init__.py` | new |
| `knowledge_base/workers/ingest/__init__.py` | `workers/ingest/__init__.py` |
| `knowledge_base/workers/ingest/worker.py` | `workers/ingest/worker.py` |
| `knowledge_base/workers/ingest/job.py` | `workers/ingest/job.py` + `tasks/ingest.py` |
| `knowledge_base/workers/ingest/chunking.py` | `workers/ingest/chunking.py` |
| `knowledge_base/workers/ingest/readers.py` | `workers/ingest/readers.py` |
| `knowledge_base/workers/ingest/progress.py` | `workers/ingest/progress.py` |
| `chat/__init__.py` | new |
| `chat/router.py` | `api/conversations.py` (routes only) |
| `chat/service.py` | business logic from `api/conversations.py` |
| `chat/repository.py` | DB queries extracted from `api/conversations.py` |
| `chat/schemas.py` | Pydantic models from `api/conversations.py` + `schemas/conversation_settings.py` |
| `chat/workers/__init__.py` | new |
| `chat/workers/memory/__init__.py` | `workers/memory/__init__.py` |
| `chat/workers/memory/extractor.py` | `workers/memory/extractor.py` |
| `chat/workers/memory/summarizer.py` | `workers/memory/summarizer.py` |

### Files that stay unchanged

`models/` (all), `tools/` (all), `scripts/` (all), `alembic/` (all).

---

## Task 1: Set up `core/` package

**Files:**
- Create: `src/ai_portal/core/__init__.py`
- Create: `src/ai_portal/core/config.py`
- Create: `src/ai_portal/core/logging.py`
- Create: `src/ai_portal/core/db/__init__.py`
- Create: `src/ai_portal/core/db/session.py`
- Create: `src/ai_portal/core/db/base.py`
- Create: `src/ai_portal/core/db/types.py`
- Create: `src/ai_portal/core/middleware/__init__.py`
- Create: `src/ai_portal/core/middleware/setup_guard.py`
- Modify (add shims): `src/ai_portal/config.py`, `src/ai_portal/logging_config.py`, `src/ai_portal/db/session.py`, `src/ai_portal/db/base.py`, `src/ai_portal/db/json_types.py`, `src/ai_portal/db/tenant.py`, `src/ai_portal/middleware/setup_guard.py`

- [ ] **Step 1: Create `core/` package files**

```bash
mkdir -p backend/src/ai_portal/core/db backend/src/ai_portal/core/middleware
touch backend/src/ai_portal/core/__init__.py
touch backend/src/ai_portal/core/db/__init__.py
touch backend/src/ai_portal/core/middleware/__init__.py
```

- [ ] **Step 2: Copy `config.py` → `core/config.py`**

Copy `backend/src/ai_portal/config.py` verbatim to `backend/src/ai_portal/core/config.py`. No changes to the file content — just the new path.

- [ ] **Step 3: Add re-export shim to old `config.py`**

Replace the entire content of `backend/src/ai_portal/config.py` with:

```python
# Re-export shim — real implementation moved to core/config.py
from ai_portal.core.config import *  # noqa: F401, F403
from ai_portal.core.config import (
    Settings,
    get_settings,
    settings_log_snapshot,
)
```

- [ ] **Step 4: Copy `logging_config.py` → `core/logging.py`**

Copy `backend/src/ai_portal/logging_config.py` verbatim to `backend/src/ai_portal/core/logging.py`.

- [ ] **Step 5: Add re-export shim to old `logging_config.py`**

```python
# Re-export shim — real implementation moved to core/logging.py
from ai_portal.core.logging import configure_logging  # noqa: F401
```

- [ ] **Step 6: Copy `db/session.py` → `core/db/session.py`**

Copy `backend/src/ai_portal/db/session.py` verbatim to `backend/src/ai_portal/core/db/session.py`.

Add shim to old `db/session.py`:
```python
from ai_portal.core.db.session import *  # noqa: F401, F403
from ai_portal.core.db.session import SessionLocal, engine
```

- [ ] **Step 7: Copy `db/base.py` → `core/db/base.py`**

Copy verbatim, add shim to old `db/base.py`:
```python
from ai_portal.core.db.base import *  # noqa: F401, F403
from ai_portal.core.db.base import Base
```

- [ ] **Step 8: Merge `db/json_types.py` + `db/tenant.py` → `core/db/types.py`**

Concatenate both files (both are small helpers) into `core/db/types.py`. Add shims to originals:

`db/json_types.py`:
```python
from ai_portal.core.db.types import *  # noqa: F401, F403
```

`db/tenant.py`:
```python
from ai_portal.core.db.types import *  # noqa: F401, F403
```

- [ ] **Step 9: Copy `middleware/setup_guard.py` → `core/middleware/setup_guard.py`**

Copy verbatim. Add shim to old file:
```python
from ai_portal.core.middleware.setup_guard import SetupGuardMiddleware  # noqa: F401
```

- [ ] **Step 10: Verify app still starts**

```bash
cd backend && python -c "from ai_portal.main import app; print('OK')"
```
Expected: `OK`

- [ ] **Step 11: Run backend tests**

```bash
cd backend && python -m pytest tests/ -x -q 2>&1 | tail -20
```
Expected: all passing (same as before).

- [ ] **Step 12: Commit**

```bash
cd backend
git add src/ai_portal/core/ src/ai_portal/config.py src/ai_portal/logging_config.py src/ai_portal/db/ src/ai_portal/middleware/
git commit -m "refactor(core): move config, logging, db, middleware to core/"
```

---

## Task 2: Set up `rag/` domain

**Files:**
- Create: `src/ai_portal/rag/__init__.py`
- Create: `src/ai_portal/rag/protocols.py`
- Create: `src/ai_portal/rag/service.py`
- Create: `src/ai_portal/rag/providers/__init__.py`
- Create: `src/ai_portal/rag/providers/voyage.py`
- Modify (add shim): `src/ai_portal/services/rag.py`, `src/ai_portal/services/embedding.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p backend/src/ai_portal/rag/providers
touch backend/src/ai_portal/rag/__init__.py
touch backend/src/ai_portal/rag/providers/__init__.py
```

- [ ] **Step 2: Create `rag/protocols.py`**

```python
# src/ai_portal/rag/protocols.py
from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
    def embeddings_missing_key_message(self) -> str: ...
```

- [ ] **Step 3: Create `rag/providers/voyage.py`**

Copy `services/embedding.py` verbatim to `rag/providers/voyage.py`. Update only the import path for `llm_connect`:

Find line:
```python
from ai_portal.services.llm_connect import normalize_openai_compatible_base
```
Replace with:
```python
from ai_portal.catalog.providers.routing import normalize_openai_compatible_base
```

> Note: `catalog/providers/routing.py` doesn't exist yet (Task 3). For now keep the old import — the shim chain will resolve it. Update in Task 3's cleanup step.

So for this task, copy verbatim with the original import intact.

- [ ] **Step 4: Add shim to `services/embedding.py`**

Replace the file content with:
```python
# Re-export shim — real implementation moved to rag/providers/voyage.py
from ai_portal.rag.providers.voyage import (  # noqa: F401
    embed_texts,
    embeddings_configured,
    embeddings_missing_key_message,
    VOYAGE_DEFAULT_EMBEDDING_MODEL,
)
```

- [ ] **Step 5: Copy `services/rag.py` → `rag/service.py`**

Copy `services/rag.py` verbatim to `rag/service.py`. Update imports at the top:

```python
# Old:
from ai_portal.services import embedding as embedding_svc
# New:
from ai_portal.rag.providers import voyage as embedding_svc
```

All function signatures and bodies remain unchanged.

- [ ] **Step 6: Add shim to `services/rag.py`**

Replace the file content with:
```python
# Re-export shim — real implementation moved to rag/service.py
from ai_portal.rag.service import (  # noqa: F401
    retrieve_context_with_meta,
)
```

- [ ] **Step 7: Update `rag/providers/__init__.py`**

```python
from ai_portal.rag.providers.voyage import (
    embed_texts,
    embeddings_configured,
    embeddings_missing_key_message,
)

# Expose as a module alias for service.py import
import ai_portal.rag.providers.voyage as voyage

__all__ = ["embed_texts", "embeddings_configured", "embeddings_missing_key_message", "voyage"]
```

- [ ] **Step 8: Verify import chain**

```bash
cd backend && python -c "from ai_portal.rag.service import retrieve_context_with_meta; print('OK')"
```
Expected: `OK`

- [ ] **Step 9: Run backend tests**

```bash
cd backend && python -m pytest tests/ -x -q 2>&1 | tail -20
```

- [ ] **Step 10: Commit**

```bash
cd backend
git add src/ai_portal/rag/ src/ai_portal/services/rag.py src/ai_portal/services/embedding.py
git commit -m "refactor(rag): move rag service and embedding providers to rag/ domain"
```

---

## Task 3: Set up `catalog/` domain

**Files:**
- Create: `src/ai_portal/catalog/__init__.py`
- Create: `src/ai_portal/catalog/router.py`
- Create: `src/ai_portal/catalog/service.py`
- Create: `src/ai_portal/catalog/repository.py`
- Create: `src/ai_portal/catalog/schemas.py`
- Create: `src/ai_portal/catalog/definitions.py`
- Create: `src/ai_portal/catalog/specs.py`
- Create: `src/ai_portal/catalog/providers/__init__.py`
- Create: `src/ai_portal/catalog/providers/protocol.py`
- Create: `src/ai_portal/catalog/providers/langchain.py`
- Create: `src/ai_portal/catalog/providers/routing.py`
- Modify (add shims): `src/ai_portal/api/model_catalog.py`, `src/ai_portal/catalog_model_definitions.py`, `src/ai_portal/catalog_specs.py`, `src/ai_portal/services/llm.py`, `src/ai_portal/services/llm_connect.py`, `src/ai_portal/services/llm_providers/`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p backend/src/ai_portal/catalog/providers
touch backend/src/ai_portal/catalog/__init__.py
touch backend/src/ai_portal/catalog/providers/__init__.py
```

- [ ] **Step 2: Create `catalog/definitions.py`**

Copy `catalog_model_definitions.py` verbatim to `catalog/definitions.py`.

Add shim to old file:
```python
from ai_portal.catalog.definitions import *  # noqa: F401, F403
from ai_portal.catalog.definitions import OPTIONAL_CATALOG_API_MODEL_IDS
```

- [ ] **Step 3: Create `catalog/specs.py`**

Copy `catalog_specs.py` verbatim to `catalog/specs.py`.

Add shim to old file:
```python
from ai_portal.catalog.specs import *  # noqa: F401, F403
```

- [ ] **Step 4: Create `catalog/providers/protocol.py`**

Copy `services/llm_providers/protocol.py` verbatim to `catalog/providers/protocol.py`.

Add shim to old file:
```python
from ai_portal.catalog.providers.protocol import ChatProvider  # noqa: F401
```

- [ ] **Step 5: Create `catalog/providers/routing.py`**

Merge `services/llm_providers/model_routing.py` and `services/llm_connect.py` into `catalog/providers/routing.py`. Place `normalize_openai_compatible_base` (from `llm_connect.py`) first, then the rest of `model_routing.py`. No logic changes.

Add shims:

`services/llm_connect.py`:
```python
from ai_portal.catalog.providers.routing import normalize_openai_compatible_base  # noqa: F401
```

`services/llm_providers/model_routing.py`:
```python
from ai_portal.catalog.providers.routing import (  # noqa: F401
    remap_deprecated_chat_model,
    normalize_model_id_for_langchain_chat,
    is_langchain_anthropic_model,
    chat_provider_credential_kwargs,
    normalize_chat_model_id_for_tests,
)
```

- [ ] **Step 6: Create `catalog/providers/langchain.py`**

Copy `services/llm_providers/langchain_chat.py` verbatim to `catalog/providers/langchain.py`. Update imports:

```python
# Old:
from ai_portal.services.llm_providers.model_routing import (...)
from ai_portal.services.llm_providers.protocol import ChatProvider
# New:
from ai_portal.catalog.providers.routing import (...)
from ai_portal.catalog.providers.protocol import ChatProvider
```

Add shim to old `services/llm_providers/langchain_chat.py`:
```python
from ai_portal.catalog.providers.langchain import LangChainChatProvider  # noqa: F401
```

- [ ] **Step 7: Update `catalog/providers/__init__.py`**

```python
from ai_portal.catalog.providers.protocol import ChatProvider
from ai_portal.catalog.providers.langchain import LangChainChatProvider
from ai_portal.catalog.providers.routing import (
    remap_deprecated_chat_model,
    normalize_model_id_for_langchain_chat,
    is_langchain_anthropic_model,
    chat_provider_credential_kwargs,
)
from ai_portal.config import Settings


def get_chat_provider(settings: Settings) -> ChatProvider:
    return LangChainChatProvider(settings)


__all__ = [
    "ChatProvider",
    "LangChainChatProvider",
    "get_chat_provider",
]
```

Update shim in `services/llm_providers/__init__.py`:
```python
from ai_portal.catalog.providers import ChatProvider, LangChainChatProvider, get_chat_provider  # noqa: F401
```

- [ ] **Step 8: Create `catalog/repository.py`**

Extract all SQLAlchemy DB queries from the services being merged into catalog. These are the `select(CatalogModel)` queries from `conversation_model_resolve.py` and `default_conversation_model.py`:

```python
# src/ai_portal/catalog/repository.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.models import CatalogModel


def get_active_catalog_model_by_slug(db: Session, slug: str) -> CatalogModel | None:
    return db.scalars(
        select(CatalogModel)
        .where(CatalogModel.slug == slug)
        .where(CatalogModel.is_active.is_(True))
        .limit(1)
    ).first()


def get_active_catalog_models_by_api_model_id(
    db: Session, api_model_id: str
) -> list[CatalogModel]:
    return list(
        db.scalars(
            select(CatalogModel)
            .where(CatalogModel.api_model_id == api_model_id)
            .where(CatalogModel.is_active.is_(True))
        ).all()
    )


def get_all_active_catalog_models(db: Session) -> list[CatalogModel]:
    return list(
        db.scalars(
            select(CatalogModel).where(CatalogModel.is_active.is_(True))
        ).all()
    )
```

- [ ] **Step 9: Create `catalog/service.py`**

Merge `services/model_access.py`, `services/catalog_model_validate.py`, `services/conversation_model_resolve.py`, `services/default_conversation_model.py` into `catalog/service.py`. Update imports to use `catalog.repository`:

```python
# src/ai_portal/catalog/service.py
from __future__ import annotations

from sqlalchemy.orm import Session

from ai_portal.catalog.definitions import OPTIONAL_CATALOG_API_MODEL_IDS
from ai_portal.catalog.repository import (
    get_active_catalog_model_by_slug,
    get_active_catalog_models_by_api_model_id,
)
from ai_portal.config import Settings, get_settings
from ai_portal.schemas.conversation_settings import CapabilityToggles, ConversationSettings

_DEFAULT_CATALOG_SLUG_PRIORITY = (
    "anthropic-claude-haiku-4-5",
    "openai-o3-mini",
)


def effective_chat_model(settings: Settings, requested: str | None) -> str:
    m = (requested or settings.chat_default_api_model).strip()
    if not m:
        raise ValueError(
            "No chat model configured (CHAT_DEFAULT_API_MODEL or per-request model)"
        )
    return m


def validate_catalog_model_id(raw: str) -> None:
    s = (raw or "").strip()
    if not s:
        raise ValueError("catalog api_model_id is empty")
    if s in OPTIONAL_CATALOG_API_MODEL_IDS:
        return


def resolve_stored_model_to_chat_model(db: Session, stored: str) -> str:
    s = (stored or "").strip()
    if not s:
        return s
    slug_row = get_active_catalog_model_by_slug(db, s)
    if slug_row is not None:
        return slug_row.api_model_id
    api_rows = get_active_catalog_models_by_api_model_id(db, s)
    if len(api_rows) == 1:
        return api_rows[0].api_model_id
    if len(api_rows) > 1:
        api_rows.sort(key=lambda r: (r.sort_order, r.id))
        return api_rows[0].api_model_id
    return s


def resolve_default_conversation_api_model(db: Session) -> str:
    for slug in _DEFAULT_CATALOG_SLUG_PRIORITY:
        row = get_active_catalog_model_by_slug(db, slug)
        if row is not None:
            return row.api_model_id
    return get_settings().chat_default_api_model


def resolve_default_conversation_stored_model(db: Session) -> str:
    for slug in _DEFAULT_CATALOG_SLUG_PRIORITY:
        row = get_active_catalog_model_by_slug(db, slug)
        if row is not None:
            return row.slug
    return get_settings().chat_default_api_model


def default_conversation_settings() -> ConversationSettings:
    return ConversationSettings(capabilities=CapabilityToggles())
```

Add shims to old service files:

`services/model_access.py`:
```python
from ai_portal.catalog.service import effective_chat_model  # noqa: F401
```

`services/catalog_model_validate.py`:
```python
from ai_portal.catalog.service import validate_catalog_model_id  # noqa: F401
```

`services/conversation_model_resolve.py`:
```python
from ai_portal.catalog.service import resolve_stored_model_to_chat_model  # noqa: F401
```

`services/default_conversation_model.py`:
```python
from ai_portal.catalog.service import (  # noqa: F401
    resolve_default_conversation_api_model,
    resolve_default_conversation_stored_model,
    default_conversation_settings,
)
```

- [ ] **Step 10: Create `catalog/schemas.py`**

Extract Pydantic models from `api/model_catalog.py` (the request/response schemas). Copy them verbatim into `catalog/schemas.py`. Keep the existing schemas in `api/model_catalog.py` for now (shim in Task 3 cleanup).

- [ ] **Step 11: Create `catalog/router.py`**

Copy `api/model_catalog.py` verbatim to `catalog/router.py`. Update imports:
```python
# Old:
# (schemas inline in the file)
# New: schemas can stay inline for now since they're staying in the file
```

Actually, copy verbatim. The `api/model_catalog.py` shim will re-export from the new location in step 12.

- [ ] **Step 12: Add shim to `api/model_catalog.py`**

```python
# Re-export shim — real implementation moved to catalog/router.py
from ai_portal.catalog.router import router  # noqa: F401
```

- [ ] **Step 13: Update `main.py` to import from new location**

In `main.py`, find:
```python
from ai_portal.api import (
    ...
    model_catalog,
    ...
)
```

This still works via the shim. Leave `main.py` unchanged for now (shim chain works).

- [ ] **Step 14: Verify**

```bash
cd backend && python -c "from ai_portal.catalog.service import resolve_stored_model_to_chat_model; print('OK')"
cd backend && python -c "from ai_portal.main import app; print('OK')"
```

- [ ] **Step 15: Run backend tests**

```bash
cd backend && python -m pytest tests/ -x -q 2>&1 | tail -20
```

- [ ] **Step 16: Fix `rag/providers/voyage.py` import**

Now that `catalog/providers/routing.py` exists, update the import in `rag/providers/voyage.py`:
```python
# Old:
from ai_portal.services.llm_connect import normalize_openai_compatible_base
# New:
from ai_portal.catalog.providers.routing import normalize_openai_compatible_base
```

- [ ] **Step 17: Commit**

```bash
cd backend
git add src/ai_portal/catalog/ src/ai_portal/catalog_model_definitions.py src/ai_portal/catalog_specs.py src/ai_portal/services/ src/ai_portal/rag/providers/voyage.py
git commit -m "refactor(catalog): move model catalog, LLM providers, and catalog services to catalog/ domain"
```

---

## Task 4: Set up `auth/` domain

**Files:**
- Create: `src/ai_portal/auth/router.py` (rename existing `api/auth.py`)
- Create: `src/ai_portal/auth/service.py` (from `services/user_identity.py`)
- Create: `src/ai_portal/auth/repository.py` (DB queries extracted from `api/auth.py` + `api/orgs.py`)
- Create: `src/ai_portal/auth/schemas.py` (Pydantic models from `api/auth.py`)
- Create: `src/ai_portal/auth/deps.py` (from `api/deps.py`)
- Create: `src/ai_portal/auth/strategies/dev.py`
- Create: `src/ai_portal/auth/strategies/entra.py`
- Create: `src/ai_portal/auth/strategies/jwt.py`
- Create: `src/ai_portal/auth/strategies/portal_keys.py`
- Modify (add shims): `src/ai_portal/api/auth.py`, `src/ai_portal/api/deps.py`, `src/ai_portal/auth/entra.py`, `src/ai_portal/auth/jwt.py`, `src/ai_portal/services/user_identity.py`, `src/ai_portal/services/portal_api_keys.py`

- [ ] **Step 1: Create directories**

```bash
mkdir -p backend/src/ai_portal/auth/strategies
touch backend/src/ai_portal/auth/strategies/__init__.py
```

- [ ] **Step 2: Move auth strategies**

Copy `auth/entra.py` → `auth/strategies/entra.py` verbatim.
Add shim to old `auth/entra.py`:
```python
from ai_portal.auth.strategies.entra import decode_entra_access_token, roles_from_claims  # noqa: F401
```

Copy `auth/jwt.py` → `auth/strategies/jwt.py` verbatim.
Add shim to old `auth/jwt.py`:
```python
from ai_portal.auth.strategies.jwt import decode_token, create_token  # noqa: F401
```

Copy `auth/password.py` → `auth/strategies/dev.py` verbatim (password/dev auth). Actually `password.py` is used by `auth/manager.py`; keep it as-is and do not rename yet. Only reorganise what the spec covers.

Actual mapping: `auth/manager.py` and `auth/password.py` contain the `UserManager` class — move them to `auth/strategies/`:

Copy `auth/manager.py` → `auth/strategies/dev.py` verbatim.
Add shim to old `auth/manager.py`:
```python
from ai_portal.auth.strategies.dev import UserManager, AuthenticationError, RegistrationError  # noqa: F401
```

Copy `auth/password.py` verbatim. It's a pure utility; leave it where it is (no domain benefit from moving it). (Auth `password.py` stays at `auth/password.py` — it has no strategy concern, just bcrypt helpers.)

- [ ] **Step 3: Move `services/portal_api_keys.py` → `auth/strategies/portal_keys.py`**

Copy `services/portal_api_keys.py` verbatim to `auth/strategies/portal_keys.py`.

Add shim to old `services/portal_api_keys.py`:
```python
from ai_portal.auth.strategies.portal_keys import (  # noqa: F401
    hash_portal_api_key,
    create_portal_api_key,
    user_for_portal_api_key,
    list_keys_for_user,
    revoke_key,
)
```

- [ ] **Step 4: Create `auth/service.py`**

Copy `services/user_identity.py` verbatim to `auth/service.py`.

Add shim to old `services/user_identity.py`:
```python
from ai_portal.auth.service import (  # noqa: F401
    profile_fields_from_claims,
    email_from_claims,
    upsert_user_from_entra_claims,
)
```

- [ ] **Step 5: Create `auth/deps.py`**

Copy `api/deps.py` verbatim to `auth/deps.py`. Update imports:
```python
# Old:
from ai_portal.auth.entra import decode_entra_access_token, roles_from_claims
from ai_portal.auth.jwt import decode_token
from ai_portal.services.portal_api_keys import user_for_portal_api_key
from ai_portal.services.user_identity import profile_fields_from_claims, upsert_user_from_entra_claims
# New:
from ai_portal.auth.strategies.entra import decode_entra_access_token, roles_from_claims
from ai_portal.auth.strategies.jwt import decode_token
from ai_portal.auth.strategies.portal_keys import user_for_portal_api_key
from ai_portal.auth.service import profile_fields_from_claims, upsert_user_from_entra_claims
```

Add shim to old `api/deps.py`:
```python
from ai_portal.auth.deps import (  # noqa: F401
    get_db,
    get_current_user,
    get_app_roles,
    get_current_org_id,
)
```

- [ ] **Step 6: Create `auth/schemas.py`**

Extract the Pydantic models from `api/auth.py` into `auth/schemas.py`:

```python
# src/ai_portal/auth/schemas.py
from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    id: int
    email: str
    role: str
    is_verified: bool
    is_superuser: bool
    org_id: str | None

    model_config = {"from_attributes": True}


class AcceptInviteRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)
```

- [ ] **Step 7: Create `auth/router.py`**

Copy `api/auth.py` verbatim to `auth/router.py`. Update the imports at the top to use the new locations:

```python
from ai_portal.auth.deps import get_db
from ai_portal.auth.strategies.jwt import decode_token
from ai_portal.auth.strategies.dev import AuthenticationError, RegistrationError, UserManager
from ai_portal.auth.schemas import (
    RegisterRequest, LoginRequest, RefreshRequest,
    TokenResponse, UserRead, AcceptInviteRequest,
)
```

Remove the inline Pydantic class definitions (they're now in `auth/schemas.py`).

Add shim to old `api/auth.py`:
```python
from ai_portal.auth.router import router  # noqa: F401
```

- [ ] **Step 8: Verify**

```bash
cd backend && python -c "from ai_portal.auth.deps import get_current_user; print('OK')"
cd backend && python -c "from ai_portal.main import app; print('OK')"
```

- [ ] **Step 9: Run tests**

```bash
cd backend && python -m pytest tests/ -x -q 2>&1 | tail -20
```

- [ ] **Step 10: Commit**

```bash
cd backend
git add src/ai_portal/auth/ src/ai_portal/api/auth.py src/ai_portal/api/deps.py src/ai_portal/services/user_identity.py src/ai_portal/services/portal_api_keys.py
git commit -m "refactor(auth): move auth strategies, deps, and user identity to auth/ domain"
```

---

## Task 5: Set up `knowledge_base/` domain

**Files:**
- Create: `src/ai_portal/knowledge_base/__init__.py`
- Create: `src/ai_portal/knowledge_base/router.py`
- Create: `src/ai_portal/knowledge_base/service.py`
- Create: `src/ai_portal/knowledge_base/repository.py`
- Create: `src/ai_portal/knowledge_base/schemas.py`
- Create: `src/ai_portal/knowledge_base/workers/ingest/` (5 files)
- Modify (add shims): `src/ai_portal/api/knowledge_bases.py`, `src/ai_portal/services/ingest_queue.py`, `src/ai_portal/workers/ingest/`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p backend/src/ai_portal/knowledge_base/workers/ingest
touch backend/src/ai_portal/knowledge_base/__init__.py
touch backend/src/ai_portal/knowledge_base/workers/__init__.py
touch backend/src/ai_portal/knowledge_base/workers/ingest/__init__.py
```

- [ ] **Step 2: Copy ingest worker files**

Copy each file verbatim to its new location:
- `workers/ingest/worker.py` → `knowledge_base/workers/ingest/worker.py`
- `workers/ingest/chunking.py` → `knowledge_base/workers/ingest/chunking.py`
- `workers/ingest/readers.py` → `knowledge_base/workers/ingest/readers.py`
- `workers/ingest/progress.py` → `knowledge_base/workers/ingest/progress.py`

For `workers/ingest/job.py`, also absorb `tasks/ingest.py` if it contains only a thin wrapper calling the worker. Check content first. Copy `workers/ingest/job.py` verbatim to `knowledge_base/workers/ingest/job.py`.

Add shims to old files:

`workers/ingest/worker.py`:
```python
from ai_portal.knowledge_base.workers.ingest.worker import *  # noqa: F401, F403
```

`workers/ingest/chunking.py`:
```python
from ai_portal.knowledge_base.workers.ingest.chunking import *  # noqa: F401, F403
```

`workers/ingest/readers.py`:
```python
from ai_portal.knowledge_base.workers.ingest.readers import *  # noqa: F401, F403
```

`workers/ingest/progress.py`:
```python
from ai_portal.knowledge_base.workers.ingest.progress import *  # noqa: F401, F403
```

`workers/ingest/job.py`:
```python
from ai_portal.knowledge_base.workers.ingest.job import *  # noqa: F401, F403
from ai_portal.knowledge_base.workers.ingest.job import run_ingest_job
```

- [ ] **Step 3: Update import paths inside the copied ingest files**

In `knowledge_base/workers/ingest/worker.py`, `job.py`, `chunking.py`, `readers.py`, `progress.py` — update any `from ai_portal.workers.ingest.*` imports to `from ai_portal.knowledge_base.workers.ingest.*`. Update `from ai_portal.services.embedding` to `from ai_portal.rag.providers.voyage`. Update `from ai_portal.services.rag` to `from ai_portal.rag.service`. Leave all other imports unchanged.

- [ ] **Step 4: Split `api/knowledge_bases.py` into schemas + repository + service + router**

Read `api/knowledge_bases.py` and identify its sections:
- Pydantic models → `knowledge_base/schemas.py`
- SQLAlchemy queries (`select(...)`, `db.add(...)`) → `knowledge_base/repository.py`
- Business logic (document state transitions, connector logic, ingest queue calls) → `knowledge_base/service.py`
- Route decorators (`@router.get`, `@router.post`, etc.) → `knowledge_base/router.py`

Create `knowledge_base/schemas.py` with all Pydantic request/response models from the file.

Create `knowledge_base/repository.py` with all DB query functions. Each function accepts `db: Session` and returns ORM instances. Example shape:

```python
# src/ai_portal/knowledge_base/repository.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.models import KnowledgeBase, Document, DocumentChunk
from ai_portal.models.connector import Connector


def get_kb_by_id(db: Session, kb_id: int, org_id) -> KnowledgeBase | None:
    return db.scalars(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.org_id == org_id,
        )
    ).first()


def list_kbs_for_org(db: Session, org_id) -> list[KnowledgeBase]:
    return list(
        db.scalars(
            select(KnowledgeBase).where(KnowledgeBase.org_id == org_id)
        ).all()
    )

# ... all other DB query functions extracted from api/knowledge_bases.py
```

Create `knowledge_base/service.py` with business logic functions. Absorb `services/ingest_queue.py` here:

```python
# src/ai_portal/knowledge_base/service.py
from __future__ import annotations

import logging
from ai_portal.knowledge_base.repository import get_kb_by_id  # etc.
from ai_portal.config import Settings, get_settings

logger = logging.getLogger(__name__)

INGEST_QUEUE_NAME = "ingest"
INGEST_JOB_FUNC = "ai_portal.knowledge_base.workers.ingest.job.run_ingest_job"


def ingest_uses_queue(settings: Settings | None = None) -> bool:
    st = settings or get_settings()
    return bool(st.redis_url.strip())


def enqueue_document_ingest(document_id: int, *, settings: Settings | None = None) -> None:
    st = settings or get_settings()
    from redis import Redis
    from rq import Queue
    conn = Redis.from_url(st.redis_url)
    q = Queue(INGEST_QUEUE_NAME, connection=conn)
    q.enqueue(
        INGEST_JOB_FUNC,
        document_id,
        job_timeout="2h",
        result_ttl=0,
        failure_ttl=86_400,
    )
    logger.info("ingest_enqueued", extra={"document_id": document_id})

# ... remaining business logic extracted from api/knowledge_bases.py
```

Add shim to `services/ingest_queue.py`:
```python
from ai_portal.knowledge_base.service import (  # noqa: F401
    ingest_uses_queue,
    enqueue_document_ingest,
    INGEST_QUEUE_NAME,
    INGEST_JOB_FUNC,
)
```

Create `knowledge_base/router.py` with the FastAPI routes. Routes call service functions, not DB directly.

Add shim to `api/knowledge_bases.py`:
```python
from ai_portal.knowledge_base.router import router  # noqa: F401
```

- [ ] **Step 5: Verify**

```bash
cd backend && python -c "from ai_portal.knowledge_base.router import router; print('OK')"
cd backend && python -c "from ai_portal.main import app; print('OK')"
```

- [ ] **Step 6: Run tests**

```bash
cd backend && python -m pytest tests/ -x -q 2>&1 | tail -20
```

- [ ] **Step 7: Commit**

```bash
cd backend
git add src/ai_portal/knowledge_base/ src/ai_portal/workers/ingest/ src/ai_portal/api/knowledge_bases.py src/ai_portal/services/ingest_queue.py
git commit -m "refactor(knowledge_base): extract KB domain with router/service/repository/schemas and absorb ingest workers"
```

---

## Task 6: Set up `chat/` domain

**Files:**
- Create: `src/ai_portal/chat/__init__.py`
- Create: `src/ai_portal/chat/router.py`
- Create: `src/ai_portal/chat/service.py`
- Create: `src/ai_portal/chat/repository.py`
- Create: `src/ai_portal/chat/schemas.py`
- Create: `src/ai_portal/chat/workers/memory/` (2 files)
- Modify (add shims): `src/ai_portal/api/conversations.py`, `src/ai_portal/workers/memory/`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p backend/src/ai_portal/chat/workers/memory
touch backend/src/ai_portal/chat/__init__.py
touch backend/src/ai_portal/chat/workers/__init__.py
touch backend/src/ai_portal/chat/workers/memory/__init__.py
```

- [ ] **Step 2: Copy memory worker files**

Copy verbatim:
- `workers/memory/extractor.py` → `chat/workers/memory/extractor.py`
- `workers/memory/summarizer.py` → `chat/workers/memory/summarizer.py`

Update internal imports in the copied files: any `from ai_portal.workers.memory.*` → `from ai_portal.chat.workers.memory.*`.

Add shims to old files:

`workers/memory/extractor.py`:
```python
from ai_portal.chat.workers.memory.extractor import *  # noqa: F401, F403
```

`workers/memory/summarizer.py`:
```python
from ai_portal.chat.workers.memory.summarizer import *  # noqa: F401, F403
```

- [ ] **Step 3: Create `chat/schemas.py`**

Extract all Pydantic models from `api/conversations.py` plus `schemas/conversation_settings.py` into `chat/schemas.py`. Add shim to old `schemas/conversation_settings.py`:
```python
from ai_portal.chat.schemas import ConversationSettings, CapabilityToggles  # noqa: F401
```

- [ ] **Step 4: Create `chat/repository.py`**

Extract all SQLAlchemy queries from `api/conversations.py` (every `db.scalars(select(...))`, `db.get(...)`, `db.add(...)`) into `chat/repository.py`. Each function takes `db: Session` as first argument and returns ORM models or primitives. Functions should match what the service layer needs. Example:

```python
# src/ai_portal/chat/repository.py
from __future__ import annotations

import uuid
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from ai_portal.models.chat import Conversation, Message


def get_conversation(db: Session, *, conversation_id: uuid.UUID, org_id: uuid.UUID) -> Conversation | None:
    return db.scalars(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.org_id == org_id,
        )
    ).first()


def list_conversations(db: Session, *, org_id: uuid.UUID) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation).where(Conversation.org_id == org_id)
            .order_by(Conversation.updated_at.desc())
        ).all()
    )

# ... all other DB query functions
```

- [ ] **Step 5: Create `chat/service.py`**

Extract all business logic from `api/conversations.py` into `chat/service.py`. This is the streaming logic, history building, starter generation, tool orchestration, and RAG retrieval calls. Import from `chat.repository`, `rag.service`, `catalog.service`, and `catalog.providers`.

The service functions should receive `Session` as a parameter (injected from the router via `Depends(get_db)`).

- [ ] **Step 6: Create `chat/router.py`**

Copy the FastAPI route decorators and handlers from `api/conversations.py` into `chat/router.py`. Each handler should:
1. Parse/validate input (Pydantic schemas)
2. Call a service function
3. Return a Pydantic response schema

Import service functions from `chat.service`. Import deps from `auth.deps`.

- [ ] **Step 7: Add shim to `api/conversations.py`**

```python
from ai_portal.chat.router import router  # noqa: F401
```

- [ ] **Step 8: Update `main.py` imports**

`main.py` still imports from `ai_portal.api.conversations` via the shim. Leave unchanged.

- [ ] **Step 9: Verify**

```bash
cd backend && python -c "from ai_portal.chat.router import router; print('OK')"
cd backend && python -c "from ai_portal.main import app; print('OK')"
```

- [ ] **Step 10: Run all backend tests**

```bash
cd backend && python -m pytest tests/ -x -q 2>&1 | tail -30
```

- [ ] **Step 11: Commit**

```bash
cd backend
git add src/ai_portal/chat/ src/ai_portal/workers/memory/ src/ai_portal/api/conversations.py
git commit -m "refactor(chat): extract chat domain with router/service/repository/schemas and absorb memory workers"
```

---

## Task 7: Update `main.py` to import from domain routers directly

Now that all domains have their own routers, update `main.py` to import from domain modules instead of via the shims in `api/`.

- [ ] **Step 1: Update `main.py`**

Replace the import block at the top of `main.py`:

```python
# Old:
from ai_portal.api import (
    auth,
    assistants,
    conversations,
    e2e,
    knowledge_bases,
    me,
    memories,
    model_catalog,
    orgs as orgs_api,
    setup as setup_api,
)
from ai_portal.config import get_settings, settings_log_snapshot
from ai_portal.logging_config import configure_logging

# New:
from ai_portal.auth.router import router as auth_router
from ai_portal.catalog.router import router as catalog_router
from ai_portal.chat.router import router as chat_router
from ai_portal.knowledge_base.router import router as knowledge_base_router
from ai_portal.api import (
    assistants,
    e2e,
    me,
    memories,
    orgs as orgs_api,
    setup as setup_api,
)
from ai_portal.core.config import get_settings, settings_log_snapshot
from ai_portal.core.logging import configure_logging
```

Replace the `app.include_router(...)` calls:

```python
# Old:
app.include_router(auth.router)
app.include_router(model_catalog.router)
app.include_router(me.router)
app.include_router(assistants.router)
app.include_router(conversations.router)
app.include_router(memories.router)
app.include_router(knowledge_bases.router)
app.include_router(setup_api.router)
app.include_router(orgs_api.router)

# New:
app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(me.router)
app.include_router(assistants.router)
app.include_router(chat_router)
app.include_router(memories.router)
app.include_router(knowledge_base_router)
app.include_router(setup_api.router)
app.include_router(orgs_api.router)
```

Also update `middleware` import:
```python
# Old:
from ai_portal.middleware.setup_guard import SetupGuardMiddleware
# New:
from ai_portal.core.middleware.setup_guard import SetupGuardMiddleware
```

- [ ] **Step 2: Verify**

```bash
cd backend && python -c "from ai_portal.main import app; print('OK')"
```

- [ ] **Step 3: Run all backend tests**

```bash
cd backend && python -m pytest tests/ -x -q 2>&1 | tail -30
```

- [ ] **Step 4: Commit**

```bash
cd backend
git add src/ai_portal/main.py
git commit -m "refactor: update main.py to import routers from domain modules directly"
```

---

## Task 8: Update remaining API files that haven't been moved yet

The files `api/assistants.py`, `api/me.py`, `api/memories.py`, `api/orgs.py`, `api/setup.py`, `api/e2e.py`, `api/rbac.py` are not part of this refactor spec — they stay in `api/` for now (out of scope). However their imports from the old locations should still work via shims.

- [ ] **Step 1: Audit remaining `api/` files for broken imports**

```bash
cd backend && python -c "
import importlib
for mod in ['ai_portal.api.assistants', 'ai_portal.api.me', 'ai_portal.api.memories', 'ai_portal.api.orgs', 'ai_portal.api.setup', 'ai_portal.api.e2e']:
    importlib.import_module(mod)
    print(f'{mod}: OK')
"
```

Expected: all print `OK`.

- [ ] **Step 2: Fix any broken imports**

If any import fails because a shim is missing, add the missing re-export shim to the old location.

- [ ] **Step 3: Run full backend test suite**

```bash
cd backend && python -m pytest tests/ -q 2>&1 | tail -30
```

All tests must pass.

- [ ] **Step 4: Commit any fixes**

```bash
cd backend
git add -p
git commit -m "refactor: fix remaining import shims for api/ files"
```

---

## Task 9: Update test imports

Tests reference the old `ai_portal.api.*` and `ai_portal.services.*` paths. The shims keep them working, but update them to import from canonical new paths.

- [ ] **Step 1: Find test files using old paths**

```bash
grep -r "from ai_portal\.\(api\|services\|workers\)" backend/tests/ --include="*.py" -l
```

- [ ] **Step 2: Update imports in each test file**

For each file found, update import paths:
- `from ai_portal.api.deps import get_db` → `from ai_portal.auth.deps import get_db`
- `from ai_portal.services.rag import ...` → `from ai_portal.rag.service import ...`
- `from ai_portal.services.embedding import ...` → `from ai_portal.rag.providers.voyage import ...`
- `from ai_portal.workers.ingest.*` → `from ai_portal.knowledge_base.workers.ingest.*`
- `from ai_portal.services.ingest_queue import ...` → `from ai_portal.knowledge_base.service import ...`

Keep shims — this step just updates tests to use canonical paths.

- [ ] **Step 3: Run full test suite**

```bash
cd backend && python -m pytest tests/ -q 2>&1 | tail -30
```

All tests must pass.

- [ ] **Step 4: Commit**

```bash
cd backend
git add backend/tests/
git commit -m "test: update test imports to use canonical domain paths"
```

---

## Task 10: Remove old shim files and empty folders

Once all consumers import from canonical new paths, delete the old shim files.

- [ ] **Step 1: Remove shim files one at a time**

For each file, remove it then verify the app still imports:

```bash
# For each old file:
rm backend/src/ai_portal/services/rag.py
python -c "from ai_portal.main import app; print('OK')"
python -m pytest backend/tests/ -q -x 2>&1 | tail -10
```

Files to delete (only after verifying nothing imports from them):
- `services/rag.py`
- `services/embedding.py`
- `services/model_access.py`
- `services/catalog_model_validate.py`
- `services/conversation_model_resolve.py`
- `services/default_conversation_model.py`
- `services/ingest_queue.py`
- `services/user_identity.py`
- `services/portal_api_keys.py`
- `services/llm.py`
- `services/llm_connect.py`
- `services/llm_providers/protocol.py`
- `services/llm_providers/model_routing.py`
- `services/llm_providers/langchain_chat.py`
- `services/llm_providers/__init__.py`
- `services/__init__.py` (after removing all above)
- `api/conversations.py`
- `api/knowledge_bases.py`
- `api/auth.py`
- `api/model_catalog.py`
- `api/deps.py`
- `catalog_model_definitions.py`
- `catalog_specs.py`
- `logging_config.py`
- `config.py` (shim — `core/config.py` is canonical now)
- Old `auth/entra.py`, `auth/jwt.py`, `auth/manager.py` (shims, not strategies)
- Old `workers/ingest/` (shim files only; real code is in `knowledge_base/workers/ingest/`)
- Old `workers/memory/` (shim files)

> Do NOT delete: `db/` (still used by alembic), `middleware/` (shim intact), `models/`, `tools/`, `scripts/`, `tasks/` (verify first)

- [ ] **Step 2: Remove `tasks/` if fully shimmed**

Check `tasks/ingest.py` and `tasks/connector_jobs.py`:
```bash
cat backend/src/ai_portal/tasks/ingest.py
cat backend/src/ai_portal/tasks/connector_jobs.py
```

If both are shims only, delete them and the `tasks/` folder.

- [ ] **Step 3: Final import verification**

```bash
cd backend && python -c "from ai_portal.main import app; print('All imports OK')"
```

- [ ] **Step 4: Run full test suite**

```bash
cd backend && python -m pytest tests/ -q 2>&1 | tail -30
```

All tests must pass.

- [ ] **Step 5: Final commit**

```bash
cd backend
git add -A
git commit -m "refactor: remove old shim files and empty legacy folders — migration complete"
```

---

## Task 11: Run E2E tests

- [ ] **Step 1: Start E2E backend**

```bash
./scripts/e2e-up.sh
```

- [ ] **Step 2: Run E2E tests**

```bash
pnpm test:e2e
```

All tests must pass.

- [ ] **Step 3: If failures**

Read the error output. Most likely cause: a shim was deleted before all consumers were updated, or `INGEST_JOB_FUNC` path changed (affects RQ task routing). Fix the specific broken import and re-run.

- [ ] **Step 4: Commit any E2E fixes**

```bash
git add -A
git commit -m "fix: resolve remaining import issues found by E2E tests"
```
