# RAG Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the enterprise RAG module: knowledge bases, document lifecycle, ~14 connectors, 8-stage ingestion pipeline with ACL mirroring, pluggable vector backends, hybrid search + RRF + rerank, external search providers, streamed answers with citations, retrieval policies, eval framework, playground, analytics, and consumer-facing REST surfaces.

**Architecture:** Extend existing `server/api/src/ai_portal/rag/` (search/answer/internal facade) and `knowledge_base/` (KB CRUD + ingest orchestrator), and add new sub-packages: `rag/connectors/`, `rag/extractors/`, `rag/chunkers/`, `rag/vector/`, `rag/search/`, `rag/acl/`, `rag/eval/`, `rag/analytics/`, `rag/policies/`. Every concrete adapter (connector, extractor, chunker, vector store, search provider, ACL mapper) implements a protocol from `<area>/protocol.py` and is discovered through a `<area>/registry.py`. All LLM / embed / rerank calls go through the **Gateway facade** — no provider SDK is imported under `rag/`. Cross-cutting concerns (auth, audit, usage, webhooks, BlobStore, settings, budgets) come from `control_plane`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x async, Alembic, Pydantic v2, pgvector (default backend), `unstructured`, `pypdf`, `python-docx`, `openpyxl`, `python-pptx`, `pytesseract`, `beautifulsoup4`, `readability-lxml`, `langchain-text-splitters`, `tree-sitter` (code-aware split), `qdrant-client`, `pinecone-client`, `weaviate-client`, `rank-bm25`, `tavily-python`, `exa-py`, `httpx`, `respx` (HTTP mocks), `pytest` + `pytest-asyncio`.

**Spec:** `docs/superpowers/specs/2026-05-28-rag-management-design.md`
**Depends on:**
- `2026-05-28-control-plane.md` (must merge first — provides `require_actor`, `require_permission`, `emit_audit`, `emit_usage`, `emit_webhook`, `BlobStore`, settings, budgets)
- `2026-05-28-gateway.md` (must merge first — provides `gateway.embed`, `gateway.complete`, `gateway.rerank`)

---

## Pre-flight

- [ ] **Step P1: Confirm worktree + branch**

```bash
git status --short
git rev-parse --abbrev-ref HEAD     # expect: pivot-rag (or assigned)
```

- [ ] **Step P2: Sync deps** — add to `server/api/pyproject.toml`:

```toml
[project.dependencies]
# extraction
unstructured = "^0.15"
pypdf = "^4.3"
python-docx = "^1.1"
openpyxl = "^3.1"
python-pptx = "^1.0"
pytesseract = "^0.3.13"
beautifulsoup4 = "^4.12"
readability-lxml = "^0.8"
# chunking
langchain-text-splitters = "^0.3"
tree-sitter = "^0.23"
tree-sitter-languages = "^1.10"
# vector backends
qdrant-client = "^1.12"
pinecone-client = "^5.0"
weaviate-client = "^4.7"
# lexical / hybrid
rank-bm25 = "^0.2"
# external search providers
tavily-python = "^0.4"
exa-py = "^1.0"
# connectors
slack-sdk = "^3.31"
notion-client = "^2.2"
atlassian-python-api = "^3.41"          # confluence + jira
PyGithub = "^2.4"
python-gitlab = "^4.10"
simple-salesforce = "^1.12"
zenpy = "^2.0"                          # zendesk
imapclient = "^3.0"                     # imap
# google / msft SDKs only used inside connectors
google-api-python-client = "^2.140"
msal = "^1.30"
```

```bash
cd server/api && uv lock && uv sync
```

- [ ] **Step P3: Confirm Control Plane + Gateway present in branch base**

```bash
python -c "from ai_portal.control_plane import require_permission, emit_audit, emit_usage, emit_webhook, BlobStore"
python -c "from ai_portal.gateway import embed, complete, rerank"
```

- [ ] **Step P4: Empty alembic revision**

```bash
cd server/api
alembic revision -m "rag: scaffolding" --autogenerate=false
# Note revision id; fill across tasks.
```

- [ ] **Step P5: Fixtures directory** — create `server/api/tests/fixtures/rag/` and commit small sample files: `sample.pdf`, `sample.docx`, `sample.xlsx`, `sample.pptx`, `sample.html`, `sample.md`, `sample.eml`, `sample.png` (with text), `sample.wav` (short clip), `sample_code.py`.

---

## Phase A — Data model + KB CRUD

### Task A1: Extend KB model to spec shape

**Files:**
- Modify: `server/api/src/ai_portal/knowledge_base/model.py` (existing `KnowledgeBase` — add `visibility`, `embedder_id`, `vector_backend`, `chunker_id`, `settings_json`, `status`, `slug`, `tags`, `default_retrieval_policy_id`, `language`)
- Migration: extend rag scaffolding revision with `ALTER TABLE` for `knowledge_bases`
- Test: `server/api/tests/knowledge_base/test_kb_model.py`

- [ ] **Step 1: Write failing test**

```python
# tests/knowledge_base/test_kb_model.py
import pytest
from ai_portal.knowledge_base.model import KnowledgeBase, KbVisibility, KbStatus

@pytest.mark.asyncio
async def test_kb_defaults_and_slug_unique(db_session, org_factory):
    org = await org_factory()
    kb = KnowledgeBase(org_id=org.id, slug="docs", name="Docs",
                       embedder_id="text-embedding-3-small", vector_backend="pgvector")
    db_session.add(kb); await db_session.commit()
    assert kb.visibility == KbVisibility.private
    assert kb.status == KbStatus.active
    assert kb.chunker_id == "fixed_token"
    db_session.add(KnowledgeBase(org_id=org.id, slug="docs", name="Dup",
                                 embedder_id="e", vector_backend="pgvector"))
    with pytest.raises(Exception):
        await db_session.commit()
```

- [ ] **Step 2: Run (expect fail)**
- [ ] **Step 3: Implement model + enums**
- [ ] **Step 4: Add migration**
- [ ] **Step 5: Apply + test**
- [ ] **Step 6: Commit**

```bash
git commit -m "feat(rag): extend KB model to spec shape (visibility, backend, chunker, status)"
```

### Task A2: KB service + router (CRUD + clone)

**Files:**
- Modify: `knowledge_base/service.py`, `repository.py`, `schemas.py`, `router.py`
- Test: `tests/knowledge_base/test_kb_service.py`

Endpoints: `POST/GET/PATCH/DELETE /v1/kbs`, `POST /v1/kbs/{id}/clone`, `POST /v1/kbs/{id}/archive`. Visibility honored on list (private→creator; team→members; org_public→all in org). RBAC: `kb:create / read / write / delete`.

- [ ] **Step 1: Failing test** — create, list filtered by visibility, archive, clone copies settings + connectors but not documents.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(rag): KB CRUD + clone + archive"
```

### Task A3: Documents + versions + chunks tables

**Files:**
- Modify: `knowledge_base/model.py` add `KbDocument`, `KbDocumentVersion`, `KbChunk`
- Migration extension: `kb_documents`, `kb_document_versions`, `kb_chunks` (with `embedding_ref`, `acl_json`, `meta_json`)
- Test: `tests/knowledge_base/test_document_model.py`

```python
class KbDocument(Base):
    __tablename__ = "kb_documents"
    id: Mapped[str] = mapped_column(primary_key=True, default=uuid_pk)
    kb_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id"), index=True)
    source_uri: Mapped[str] = mapped_column(String(2048), index=True)
    title: Mapped[str] = mapped_column(String(512))
    mime: Mapped[str] = mapped_column(String(128))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    source_acl_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus), default=DocStatus.pending)
    latest_version_id: Mapped[str | None] = mapped_column(nullable=True)
    quarantine_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (UniqueConstraint("kb_id", "source_uri", name="uq_kb_doc_uri"),)
```

- [ ] **Step 1: Failing test** — insert doc/version/chunk; `(kb_id, source_uri)` unique; cascade delete from KB.
- [ ] **Step 2–6**: Implement, migrate, commit.

```bash
git commit -m "feat(rag): kb_documents + kb_document_versions + kb_chunks tables"
```

### Task A4: Document REST surface (upload / paste / URL)

**Files:**
- Modify: `knowledge_base/router.py` (`POST /v1/kbs/{id}/documents`, `GET …`, `DELETE …`, `POST …/{doc_id}/reingest`)
- Modify: `knowledge_base/service.py` for upload-to-BlobStore + enqueue ingest job
- Test: `tests/knowledge_base/test_document_router.py`

- [ ] **Step 1: Failing tests** — multipart upload, paste text, paste URL each enqueue an ingest job; tombstone on delete (vector purge job emitted); reingest replays pipeline.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(rag): document upload/url/text REST surface + tombstone"
```

### Task A5: Per-KB API key (read-only, scoped)

**Files:**
- Modify: `knowledge_base/service.py` add `mint_scoped_key(kb_id)` using `control_plane.api_keys.create(scopes=["kb:read", "kb:answer"], resource=kb_id)`
- Test: `tests/knowledge_base/test_scoped_key.py`

- [ ] **Step 1: Failing test** — key resolves an Actor whose permissions only pass on the bound KB.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(rag): per-KB read-only scoped API key"
```

---

## Phase B — Vector store abstraction

### Task B1: VectorStore protocol + registry

**Files:**
- Create: `server/api/src/ai_portal/rag/vector/protocol.py`
- Create: `rag/vector/registry.py`
- Test: `tests/rag/vector/test_protocol.py`

```python
# protocol.py
from typing import Protocol, AsyncIterator
from dataclasses import dataclass

@dataclass
class VectorPoint:
    id: str
    embedding: list[float]
    payload: dict             # text, doc_id, chunk_id, acl, meta

@dataclass
class VectorHit:
    id: str
    score: float
    payload: dict

@dataclass
class VectorFilter:
    must: dict | None = None  # exact-match terms
    must_not: dict | None = None
    range: dict | None = None # e.g. {"created_at": {"gte": ...}}

class VectorStore(Protocol):
    name: str
    async def upsert(self, ns: str, points: list[VectorPoint]) -> None: ...
    async def delete(self, ns: str, ids: list[str]) -> None: ...
    async def query(self, ns: str, vec: list[float], top_k: int,
                    flt: VectorFilter | None = None) -> list[VectorHit]: ...
    async def count(self, ns: str, flt: VectorFilter | None = None) -> int: ...
    async def ensure_namespace(self, ns: str, dim: int) -> None: ...
```

- [ ] **Step 1: Failing test** — fake store implements protocol; registry resolves by name + raises on duplicate registration.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(rag): VectorStore protocol + registry"
```

### Task B2: pgvector backend (default)

**Files:**
- Create: `rag/vector/backends/pgvector.py`
- Migration extension: `kb_chunk_embeddings(chunk_id PK, kb_id, embedding vector(?), meta_json, acl_json)` + IVFFLAT/HNSW index per namespace dim
- Test: `tests/rag/vector/test_pgvector.py`

- [ ] **Step 1: Failing test** — upsert 100 random vectors dim=384; query nearest of a known vector returns it within top-3; filter by `must={"kb_id": …}` excludes other namespaces.
- [ ] **Step 2–6**: Implement; dim resolved per namespace; commit.

```bash
git commit -m "feat(rag): pgvector backend"
```

### Task B3: Qdrant backend

**Files:**
- Create: `rag/vector/backends/qdrant.py` (uses `qdrant-client.AsyncQdrantClient`)
- Test: `tests/rag/vector/test_qdrant.py` (run against `qdrant_client.local.QdrantLocal`)

- [ ] **Step 1: Failing test** — upsert + query + filter parity with pgvector backend.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(rag): qdrant vector backend"
```

### Task B4: Pinecone backend

**Files:**
- Create: `rag/vector/backends/pinecone.py`
- Test: `tests/rag/vector/test_pinecone.py` (respx-mock the Pinecone REST API)

- [ ] **Step 1: Failing test** — `ensure_namespace` POSTs index create; `upsert` batches at 100; `query` translates filters to Pinecone metadata-filter syntax.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(rag): pinecone vector backend"
```

### Task B5: Weaviate backend

**Files:**
- Create: `rag/vector/backends/weaviate.py`
- Test: `tests/rag/vector/test_weaviate.py` (respx-mock REST + gRPC where feasible, else integration-marker skip)

- [ ] **Step 1–6**: Implement parity test suite; commit.

```bash
git commit -m "feat(rag): weaviate vector backend"
```

### Task B6: Resolve backend per-KB

**Files:**
- Create: `rag/vector/resolver.py` → `get_store(kb) -> VectorStore`
- Test: `tests/rag/vector/test_resolver.py`

- [ ] **Step 1: Failing test** — KB with `vector_backend="qdrant"` resolves to QdrantBackend instance; unknown id raises `UnknownVectorBackend`.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(rag): per-KB vector backend resolver"
```

---

## Phase C — Extractors

### Task C1: Extractor protocol + registry

**Files:**
- Create: `rag/extractors/protocol.py`, `rag/extractors/registry.py`
- Test: `tests/rag/extractors/test_protocol.py`

```python
# protocol.py
from typing import Protocol
from dataclasses import dataclass

@dataclass
class ExtractedDocument:
    text: str
    blocks: list["Block"]          # paragraph | heading | table | code | image_caption
    meta: dict                     # title, author, created_at, language, page_count

class Extractor(Protocol):
    name: str
    mime_types: set[str]
    def supports(self, mime: str) -> bool: ...
    async def extract(self, data: bytes, meta: dict) -> ExtractedDocument: ...
```

- [ ] **Step 1: Failing test** — registry dispatches by mime; `text/plain` resolves built-in plain extractor; unknown mime raises `NoExtractor`.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(rag): Extractor protocol + mime dispatch registry"
```

### Task C2: PDF extractor (exemplar — full TDD)

**Files:**
- Create: `rag/extractors/pdf.py` (uses `pypdf` for text, falls back to `unstructured.partition.pdf` for layout)
- Test: `tests/rag/extractors/test_pdf.py`

- [ ] **Step 1: Failing test**

```python
# tests/rag/extractors/test_pdf.py
import pytest
from pathlib import Path
from ai_portal.rag.extractors.pdf import PdfExtractor

FIX = Path(__file__).parent.parent.parent / "fixtures" / "rag"

@pytest.mark.asyncio
async def test_pdf_extracts_text_and_pages():
    ext = PdfExtractor()
    assert ext.supports("application/pdf")
    data = (FIX / "sample.pdf").read_bytes()
    doc = await ext.extract(data, meta={"source_uri": "file:///sample.pdf"})
    assert "Knowledge Base" in doc.text       # known token in fixture
    assert doc.meta["page_count"] >= 1
    headings = [b for b in doc.blocks if b.kind == "heading"]
    assert len(headings) >= 1

@pytest.mark.asyncio
async def test_pdf_extracts_table_block():
    ext = PdfExtractor()
    data = (FIX / "sample_with_table.pdf").read_bytes()
    doc = await ext.extract(data, meta={})
    tables = [b for b in doc.blocks if b.kind == "table"]
    assert len(tables) == 1
    assert tables[0].rows[0][0] == "Col A"
```

- [ ] **Step 2: Run (expect fail)**
- [ ] **Step 3: Implement**

```python
# rag/extractors/pdf.py
from dataclasses import dataclass
from pypdf import PdfReader
from io import BytesIO
from .protocol import Extractor, ExtractedDocument
from .blocks import Block, ParagraphBlock, HeadingBlock, TableBlock

class PdfExtractor:
    name = "pdf"
    mime_types = {"application/pdf"}

    def supports(self, mime: str) -> bool:
        return mime in self.mime_types

    async def extract(self, data: bytes, meta: dict) -> ExtractedDocument:
        reader = PdfReader(BytesIO(data))
        blocks: list[Block] = []
        text_parts: list[str] = []
        for page_no, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            for line in page_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if self._looks_like_heading(line):
                    blocks.append(HeadingBlock(text=line, level=1, page=page_no))
                else:
                    blocks.append(ParagraphBlock(text=line, page=page_no))
            text_parts.append(page_text)
        # tables via unstructured (lazy import — costly)
        try:
            from unstructured.partition.pdf import partition_pdf
            for el in partition_pdf(file=BytesIO(data), strategy="fast"):
                if el.category == "Table":
                    blocks.append(TableBlock(rows=self._parse_html_table(el.metadata.text_as_html)))
        except Exception:
            pass
        return ExtractedDocument(
            text="\n".join(text_parts),
            blocks=blocks,
            meta={
                **meta,
                "page_count": len(reader.pages),
                "title": (reader.metadata or {}).get("/Title") if reader.metadata else None,
            },
        )

    @staticmethod
    def _looks_like_heading(line: str) -> bool:
        return len(line) < 80 and (line.isupper() or line.endswith(":"))

    @staticmethod
    def _parse_html_table(html: str | None) -> list[list[str]]:
        if not html:
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        return [[c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                for row in soup.find_all("tr")]
```

- [ ] **Step 4: Run (expect pass)**
- [ ] **Step 5: Register in registry import**
- [ ] **Step 6: Commit**

```bash
git commit -m "feat(rag): PDF extractor (text + tables + headings)"
```

### Task C3: DOCX extractor

**Files:** `rag/extractors/docx.py` using `python-docx`; preserves heading levels + tables.
**Test:** `tests/rag/extractors/test_docx.py` — fixture with H1/H2 and one table → asserts heading blocks have correct level and table parsed.

```bash
git commit -m "feat(rag): DOCX extractor"
```

### Task C4: XLSX extractor

**Files:** `rag/extractors/xlsx.py` using `openpyxl`; each sheet → one `TableBlock` with sheet name in meta.
**Test:** asserts sheet count + first-row header values.

```bash
git commit -m "feat(rag): XLSX extractor"
```

### Task C5: PPTX extractor

**Files:** `rag/extractors/pptx.py` using `python-pptx`; one paragraph per slide text-frame, slide notes appended.
**Test:** slide count from fixture matches.

```bash
git commit -m "feat(rag): PPTX extractor"
```

### Task C6: HTML extractor (readability)

**Files:** `rag/extractors/html.py` using `readability-lxml` + `beautifulsoup4`; strips nav/script/style.
**Test:** noisy HTML fixture → only main article text retained; meta `title` extracted.

```bash
git commit -m "feat(rag): HTML extractor (readability)"
```

### Task C7: Markdown / RST / AsciiDoc extractor

**Files:** `rag/extractors/markdown.py` — split by ATX/setext headings into structural blocks.
**Test:** fixture with `# H1` and `## H2` → block levels 1, 2.

```bash
git commit -m "feat(rag): Markdown/RST/AsciiDoc extractor"
```

### Task C8: Email (.eml / .msg) extractor

**Files:** `rag/extractors/email.py` — uses stdlib `email.parser`; `extract-msg` lazy for .msg.
**Test:** .eml fixture → subject in meta, from/to/date populated, body text returned.

```bash
git commit -m "feat(rag): email (.eml/.msg) extractor"
```

### Task C9: Image OCR extractor

**Files:** `rag/extractors/image_ocr.py` — `pytesseract` default, cloud-OCR provider behind setting.
**Test:** PNG fixture containing "HELLO RAG" → extracted text contains "HELLO RAG".

```bash
git commit -m "feat(rag): image OCR extractor (Tesseract default)"
```

### Task C10: Audio transcription extractor

**Files:** `rag/extractors/audio_transcribe.py` — routes through `gateway.transcribe(...)` (Whisper-class model alias); no SDK imported directly.
**Test:** mocks gateway to return canned transcript; asserts text+segments forwarded.

```bash
git commit -m "feat(rag): audio transcribe extractor (gateway-routed)"
```

### Task C11: Code extractor (language-tagged)

**Files:** `rag/extractors/code.py` — detects language via file extension + `pygments` lexer; tokenises into function-level blocks via `tree-sitter`.
**Test:** Python fixture → 2 function blocks each with `language="python"` in meta.

```bash
git commit -m "feat(rag): code extractor (language detection + AST blocks)"
```

### Task C12: Plain text + source-code fallback

**Files:** `rag/extractors/plain.py` — default for `text/*` when no specialist applies; returns single paragraph block with detected language.
**Test:** UTF-8 + Latin-1 inputs both decode without exception.

```bash
git commit -m "feat(rag): plain-text fallback extractor"
```

---

## Phase D — Chunkers

### Task D1: Chunker protocol + registry

**Files:**
- Create: `rag/chunkers/protocol.py`, `rag/chunkers/registry.py`
- Test: `tests/rag/chunkers/test_protocol.py`

```python
# protocol.py
from typing import Protocol, AsyncIterator
from dataclasses import dataclass

@dataclass
class ChunkOpts:
    max_tokens: int = 512
    overlap_tokens: int = 64
    extra: dict | None = None

@dataclass
class Chunk:
    text: str
    index: int
    token_count: int
    meta: dict           # heading_path, page, function, language

class Chunker(Protocol):
    name: str
    async def chunk(self, doc: ExtractedDocument, opts: ChunkOpts) -> AsyncIterator[Chunk]: ...
```

- [ ] **Step 1–6**: Implement protocol + registry + tiktoken-based token counter; commit.

```bash
git commit -m "feat(rag): Chunker protocol + registry"
```

### Task D2: Fixed-token chunker (exemplar)

**Files:** `rag/chunkers/fixed_token.py` using `langchain_text_splitters.TokenTextSplitter`.
**Test:** `tests/rag/chunkers/test_fixed_token.py`

```python
@pytest.mark.asyncio
async def test_fixed_token_respects_max_and_overlap():
    doc = ExtractedDocument(text="word " * 2000, blocks=[], meta={})
    chunker = FixedTokenChunker()
    chunks = [c async for c in chunker.chunk(doc, ChunkOpts(max_tokens=256, overlap_tokens=32))]
    assert all(c.token_count <= 256 for c in chunks)
    # overlap: shared tokens between adjacent chunks
    assert chunks[0].text.split()[-8:] == chunks[1].text.split()[:8]
```

```bash
git commit -m "feat(rag): fixed-token chunker"
```

### Task D3: Sentence chunker

**Files:** `rag/chunkers/sentence.py` — sentence-tokeniser (`nltk.punkt` lazy); packs sentences up to budget.
**Test:** asserts every chunk ends on a sentence terminator.

```bash
git commit -m "feat(rag): sentence chunker"
```

### Task D4: Semantic chunker (embedding-based break)

**Files:** `rag/chunkers/semantic.py` — embeds each sentence via `gateway.embed`; splits at largest cosine gap above threshold.
**Test:** synthetic doc of 3 topical paragraphs → 3 chunks.

```bash
git commit -m "feat(rag): semantic chunker (embedding-break)"
```

### Task D5: Structural chunker

**Files:** `rag/chunkers/structural.py` — splits at heading boundaries; `heading_path` propagated into meta.
**Test:** fixture HTML with H1/H2 → chunks carry `meta["heading_path"]` like `["Intro", "Goals"]`.

```bash
git commit -m "feat(rag): structural (heading-aware) chunker"
```

### Task D6: Code-aware chunker

**Files:** `rag/chunkers/code_aware.py` — uses tree-sitter to split at function / class boundaries; respects token budget.
**Test:** Python fixture → each chunk has `meta["function"]` populated.

```bash
git commit -m "feat(rag): code-aware (AST) chunker"
```

---

## Phase E — Connector framework

### Task E1: Connector protocol + manifest + registry

**Files:**
- Create: `rag/connectors/protocol.py`, `rag/connectors/manifest.py`, `rag/connectors/registry.py`
- Test: `tests/rag/connectors/test_protocol.py`

```python
# protocol.py
from typing import Protocol, AsyncIterator
from dataclasses import dataclass

@dataclass
class SourceDoc:
    source_uri: str
    title: str
    mime: str | None
    size: int | None
    modified_at: datetime | None
    cursor_token: str | None        # for delta replay
    raw: dict                       # connector-native passthrough

@dataclass
class FetchedDoc:
    data: bytes
    mime: str
    meta: dict

@dataclass
class AclSet:
    user_ids: set[str]
    group_ids: set[str]
    public: bool = False

@dataclass
class ConnectorManifest:
    name: str
    auth_kinds: tuple[str, ...]     # "oauth", "token", "service_principal", "basic"
    schedulable: bool
    supports_delta: bool
    supports_acl: bool
    supports_webhook: bool
    config_schema: dict             # JSON schema

class Connector(Protocol):
    manifest: ConnectorManifest
    @classmethod
    async def setup(cls, config: dict, secret_store) -> "Connector": ...
    async def discover(self, cursor: str | None) -> AsyncIterator[SourceDoc]: ...
    async def fetch(self, sd: SourceDoc) -> FetchedDoc: ...
    async def acls(self, sd: SourceDoc) -> AclSet: ...
    async def delta_cursor(self) -> str | None: ...
    async def apply_delta_cursor(self, cursor: str) -> None: ...
```

- [ ] **Step 1: Failing test** — registry rejects connector missing manifest; resolves by name.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(rag): Connector protocol + manifest + registry"
```

### Task E2: kb_connectors + sync_runs + sync_errors tables

**Files:**
- Modify: `knowledge_base/model.py` add `KbConnector`, `KbSyncRun`, `KbSyncError`
- Migration extension
- Test: `tests/knowledge_base/test_connector_model.py`

`kb_connectors(id, kb_id, kind, config_encrypted, schedule_cron, last_sync_at, last_cursor, enabled)`. Config encrypted at rest (AES-GCM, KEK from Control Plane).

- [ ] **Step 1: Failing test** — store + retrieve connector; ciphertext on disk; decrypts in service.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(rag): kb_connectors + sync_runs + sync_errors tables"
```

### Task E3: Sync orchestrator + scheduler

**Files:**
- Create: `rag/connectors/sync_service.py`, `rag/connectors/scheduler.py` (cron loop, asyncio)
- Test: `tests/rag/connectors/test_sync_service.py`

Orchestrator loop:
1. Load connector by id → instantiate via manifest
2. Begin `KbSyncRun`
3. `for sd in connector.discover(cursor):` → enqueue `IngestJob(doc_uri=sd.source_uri, connector_id=…)`
4. Persist new cursor on success; record `KbSyncError` on any per-doc failure (sync continues)
5. Honor 429 `Retry-After` with exponential backoff
6. Emit `kb.sync_complete` / `kb.sync_failed` webhook + audit

- [ ] **Step 1: Failing test** — fake connector yields 5 docs; sync_service creates 5 ingest jobs + 1 sync_run row. Re-run with same cursor yields 0.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(rag): sync orchestrator + scheduler + delta cursor"
```

### Task E4: Connector REST surface + manual trigger

**Files:**
- Modify: `knowledge_base/router.py` — `POST /v1/kbs/{id}/connectors`, `GET …`, `PATCH …`, `DELETE …`, `POST …/{cid}/sync`, `GET …/{cid}/runs`
- Test: `tests/knowledge_base/test_connector_router.py`

- [ ] **Step 1–6**: Implement, commit.

```bash
git commit -m "feat(rag): connector REST surface + manual sync"
```

---

## Phase F — Connectors (concrete adapters)

### Task F1: Web Crawler connector (EXEMPLAR — full TDD)

**Files:**
- Create: `rag/connectors/adapters/web_crawler.py`
- Test: `tests/rag/connectors/test_web_crawler.py`

- [ ] **Step 1: Write failing test**

```python
# tests/rag/connectors/test_web_crawler.py
import pytest, respx, httpx
from ai_portal.rag.connectors.adapters.web_crawler import WebCrawlerConnector

SITEMAP_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://acme.test/docs/a</loc><lastmod>2026-05-01</lastmod></url>
  <url><loc>https://acme.test/docs/b</loc></url>
</urlset>"""

ROBOTS_TXT = b"""User-agent: *
Allow: /docs/
Disallow: /private/
"""

@pytest.mark.asyncio
async def test_web_crawler_respects_robots_and_emits_sitemap_urls(secret_store):
    with respx.mock(base_url="https://acme.test") as m:
        m.get("/robots.txt").mock(httpx.Response(200, content=ROBOTS_TXT))
        m.get("/sitemap.xml").mock(httpx.Response(200, content=SITEMAP_XML))
        m.get("/docs/a").mock(httpx.Response(200, text="<html><body>A</body></html>",
                                              headers={"content-type": "text/html"}))
        m.get("/docs/b").mock(httpx.Response(200, text="<html><body>B</body></html>",
                                              headers={"content-type": "text/html"}))
        m.get("/private/secret").mock(httpx.Response(200, text="nope"))
        conn = await WebCrawlerConnector.setup(
            config={"seed_urls": ["https://acme.test/sitemap.xml",
                                  "https://acme.test/private/secret"],
                    "rate_per_domain_rps": 5},
            secret_store=secret_store,
        )
        urls = [sd.source_uri async for sd in conn.discover(cursor=None)]
        assert "https://acme.test/docs/a" in urls
        assert "https://acme.test/docs/b" in urls
        assert "https://acme.test/private/secret" not in urls  # robots blocked

@pytest.mark.asyncio
async def test_web_crawler_delta_cursor_emits_lastmod():
    conn = await WebCrawlerConnector.setup(config={"seed_urls": []}, secret_store=None)
    await conn.apply_delta_cursor("2026-05-02T00:00:00Z")
    # subsequent discover skips docs with lastmod earlier than cursor
```

- [ ] **Step 2: Run (expect fail)**
- [ ] **Step 3: Implement**

```python
# rag/connectors/adapters/web_crawler.py
import asyncio, httpx
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
from datetime import datetime
from xml.etree import ElementTree as ET
from ..protocol import Connector, ConnectorManifest, SourceDoc, FetchedDoc, AclSet

MANIFEST = ConnectorManifest(
    name="web_crawler",
    auth_kinds=("none",),
    schedulable=True,
    supports_delta=True,         # via lastmod
    supports_acl=False,
    supports_webhook=False,
    config_schema={
        "type": "object",
        "required": ["seed_urls"],
        "properties": {
            "seed_urls": {"type": "array", "items": {"type": "string"}},
            "max_depth": {"type": "integer", "default": 3},
            "rate_per_domain_rps": {"type": "number", "default": 1.0},
            "respect_robots": {"type": "boolean", "default": True},
        },
    },
)

class WebCrawlerConnector:
    manifest = MANIFEST

    def __init__(self, config: dict):
        self._config = config
        self._cursor: str | None = None
        self._robots: dict[str, RobotFileParser] = {}
        self._semaphore_per_host: dict[str, asyncio.Semaphore] = {}

    @classmethod
    async def setup(cls, config: dict, secret_store) -> "WebCrawlerConnector":
        return cls(config)

    async def _robots_for(self, client: httpx.AsyncClient, host: str) -> RobotFileParser:
        if host in self._robots:
            return self._robots[host]
        rp = RobotFileParser()
        try:
            res = await client.get(f"https://{host}/robots.txt")
            rp.parse(res.text.splitlines())
        except Exception:
            pass
        self._robots[host] = rp
        return rp

    async def discover(self, cursor):
        cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00")) if cursor else None
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            for seed in self._config["seed_urls"]:
                async for sd in self._walk_seed(client, seed, cursor_dt):
                    yield sd

    async def _walk_seed(self, client, seed, cursor_dt):
        host = urlparse(seed).netloc
        rp = await self._robots_for(client, host) if self._config.get("respect_robots", True) else None
        if seed.endswith(".xml"):
            async for sd in self._iter_sitemap(client, seed, rp, cursor_dt, host):
                yield sd
        else:
            if rp and not rp.can_fetch("*", seed):
                return
            yield SourceDoc(source_uri=seed, title=seed, mime="text/html",
                            size=None, modified_at=None, cursor_token=None, raw={})

    async def _iter_sitemap(self, client, url, rp, cursor_dt, host):
        res = await client.get(url)
        root = ET.fromstring(res.content)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        for u in root.findall("sm:url", ns):
            loc = u.findtext("sm:loc", namespaces=ns)
            lastmod_raw = u.findtext("sm:lastmod", namespaces=ns)
            lastmod = datetime.fromisoformat(lastmod_raw) if lastmod_raw else None
            if rp and not rp.can_fetch("*", loc):
                continue
            if cursor_dt and lastmod and lastmod <= cursor_dt:
                continue
            yield SourceDoc(source_uri=loc, title=loc, mime="text/html",
                            size=None, modified_at=lastmod,
                            cursor_token=lastmod.isoformat() if lastmod else None, raw={})

    async def fetch(self, sd):
        rps = self._config.get("rate_per_domain_rps", 1.0)
        host = urlparse(sd.source_uri).netloc
        sem = self._semaphore_per_host.setdefault(host, asyncio.Semaphore(max(1, int(rps))))
        async with sem, httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            r = await client.get(sd.source_uri)
            r.raise_for_status()
            return FetchedDoc(data=r.content,
                              mime=r.headers.get("content-type", "text/html").split(";")[0],
                              meta={"status": r.status_code, "etag": r.headers.get("etag")})

    async def acls(self, sd): return AclSet(user_ids=set(), group_ids=set(), public=True)
    async def delta_cursor(self): return self._cursor
    async def apply_delta_cursor(self, cursor): self._cursor = cursor
```

- [ ] **Step 4: Run (expect pass)**
- [ ] **Step 5: Register in `rag/connectors/adapters/__init__.py`**
- [ ] **Step 6: Commit**

```bash
git commit -m "feat(rag): web crawler connector (sitemap + robots + delta + rate-limit)"
```

### Task F2: File upload connector

**Files:** `rag/connectors/adapters/file_upload.py` — pulls from BlobStore prefix; no auth required (BlobStore credentials managed by Control Plane).
**Test scenario:** seed 3 blobs under prefix → discover yields 3 SourceDoc; manifest `supports_delta=True` via etag.

```bash
git commit -m "feat(rag): file upload connector"
```

### Task F3: S3 connector

**Files:** `rag/connectors/adapters/s3.py` — uses `aioboto3`; prefix watch + ETag delta cursor.
**Test scenario:** moto-mocked bucket with 2 objects → discover yields 2 SourceDocs with correct keys + sizes.

```bash
git commit -m "feat(rag): S3 connector"
```

### Task F4: Azure Blob connector

**Files:** `rag/connectors/adapters/azure_blob.py` — `azure-storage-blob` async; service-principal auth.
**Test scenario:** respx-mock list blobs → yields all under container/prefix.

```bash
git commit -m "feat(rag): Azure Blob connector"
```

### Task F5: GCS connector

**Files:** `rag/connectors/adapters/gcs.py` — `google-cloud-storage`; service-account JSON via secret store.
**Test scenario:** mocked list → yields blobs; supports delta via generation.

```bash
git commit -m "feat(rag): GCS connector"
```

### Task F6: Google Drive connector

**Files:** `rag/connectors/adapters/gdrive.py` — `google-api-python-client`; OAuth; folder + shared-drive scope; ACL via `permissions.list`.
**Test scenario:** mocked Drive API → discover yields files; `acls()` returns user emails + group ids.

```bash
git commit -m "feat(rag): Google Drive connector (with ACL extraction)"
```

### Task F7: OneDrive / Sharepoint connector

**Files:** `rag/connectors/adapters/sharepoint.py` — MS Graph via `msal`; site + library scope; ACL via Graph `permissions`.
**Test scenario:** respx-mock Graph drive children → yields files; ACL maps to AAD users/groups.

```bash
git commit -m "feat(rag): OneDrive/Sharepoint connector"
```

### Task F8: Confluence connector

**Files:** `rag/connectors/adapters/confluence.py` — `atlassian-python-api`; cloud + server modes; ACL via space restrictions.
**Test scenario:** mocked pages list → yields pages with `meta["space"]`, `meta["version"]`.

```bash
git commit -m "feat(rag): Confluence connector"
```

### Task F9: Notion connector

**Files:** `rag/connectors/adapters/notion.py` — `notion-client`; workspace token; databases + pages traversal.
**Test scenario:** mocked workspace → yields one database row + one page; properties flattened into meta.

```bash
git commit -m "feat(rag): Notion connector"
```

### Task F10: Slack connector

**Files:** `rag/connectors/adapters/slack.py` — `slack-sdk` async; bot install; channel allow list; threads + file shares; ACL via channel members.
**Test scenario:** mocked conversations.history + replies → yields one root message + 2 replies as separate SourceDocs.

```bash
git commit -m "feat(rag): Slack connector (channels + threads + files)"
```

### Task F11: GitHub connector

**Files:** `rag/connectors/adapters/github.py` — `PyGithub`; org/repo scope; ingests README + docs/ + issues + PRs + wiki.
**Test scenario:** mocked repo → yields README + one issue; ACL=collaborators.

```bash
git commit -m "feat(rag): GitHub connector (code + docs + issues + PRs + wiki)"
```

### Task F12: GitLab connector

**Files:** `rag/connectors/adapters/gitlab.py` — `python-gitlab`; group/project scope.
**Test scenario:** mocked project → yields README + one issue.

```bash
git commit -m "feat(rag): GitLab connector"
```

### Task F13: IMAP / shared mailbox connector

**Files:** `rag/connectors/adapters/imap.py` — `imapclient` async wrapper; label filter; attachment extraction.
**Test scenario:** in-memory IMAP fake → yields 2 emails with attachments as child SourceDocs.

```bash
git commit -m "feat(rag): IMAP shared-mailbox connector"
```

### Task F14: Salesforce Knowledge connector

**Files:** `rag/connectors/adapters/salesforce.py` — `simple-salesforce`; production org; KnowledgeArticleVersion soql.
**Test scenario:** mocked query → yields 2 articles with categories in meta.

```bash
git commit -m "feat(rag): Salesforce Knowledge connector"
```

### Task F15: Zendesk / Intercom connector

**Files:** `rag/connectors/adapters/zendesk.py`, `rag/connectors/adapters/intercom.py` — articles + (opt-in) tickets.
**Test scenario:** Zendesk help-center API mocked → yields articles; tickets only when `config.tickets_opt_in=True`.

```bash
git commit -m "feat(rag): Zendesk + Intercom connectors"
```

### Task F16: Jira connector

**Files:** `rag/connectors/adapters/jira.py` — `atlassian-python-api`; project scope; issue body + comments + attachments.
**Test scenario:** mocked Jira → yields 1 issue with attachment child SourceDoc.

```bash
git commit -m "feat(rag): Jira connector"
```

### Task F17: Generic HTTP API connector

**Files:** `rag/connectors/adapters/http_generic.py` — cursor-paginated; JSONPath extractors mapped to `(source_uri, title, body, modified_at)`; auth via bearer/basic/api-key.
**Test scenario:** respx-mocked endpoint returning paginated JSON → yields all pages flattened; cursor persisted.

```bash
git commit -m "feat(rag): generic HTTP API connector (JSONPath-configured)"
```

---

## Phase G — 8-stage ingestion pipeline

### Task G1: Job + step models

**Files:**
- Modify: `knowledge_base/model.py` add `KbIngestJob`, `KbIngestStep`
- Migration extension
- Test: `tests/knowledge_base/test_ingest_models.py`

`kb_ingest_jobs(id, document_id, status, started_at, ended_at)`; `kb_ingest_steps(id, job_id, stage, status, started_at, ended_at, error, payload_ref)`. Stages enum: `fetch, extract, normalize, redact, chunk, enrich, embed, index`.

- [ ] **Step 1–6**: Implement, commit.

```bash
git commit -m "feat(rag): ingest jobs + steps tables"
```

### Task G2: Pipeline runner + retry/failure-isolation

**Files:**
- Modify: `knowledge_base/ingest_service.py` (existing — refactor into staged runner)
- Create: `rag/pipeline/runner.py`
- Test: `tests/rag/pipeline/test_runner.py`

```python
# rag/pipeline/runner.py
class PipelineRunner:
    STAGES = ("fetch", "extract", "normalize", "redact",
              "chunk", "enrich", "embed", "index")

    def __init__(self, deps: PipelineDeps):
        self.d = deps

    async def run(self, job_id: str) -> None:
        job = await self.d.jobs.get(job_id)
        ctx = StageCtx(job=job, doc=None, extracted=None, chunks=None, embeddings=None)
        for stage in self.STAGES:
            step = await self.d.steps.start(job.id, stage)
            try:
                ctx = await getattr(self, f"_stage_{stage}")(ctx)
                await self.d.steps.complete(step.id)
            except Exception as e:
                await self.d.steps.fail(step.id, str(e))
                await self.d.docs.quarantine(job.document_id, reason=f"{stage}: {e}")
                await self.d.audit.emit("kb.doc.quarantine",
                                        resource_id=job.document_id, payload={"stage": stage, "error": str(e)})
                return                                          # failure-isolated to this doc
        await self.d.docs.mark_indexed(job.document_id)
```

- [ ] **Step 1: Failing test** — happy path: 8 steps recorded, doc status=indexed. Failure at `embed` quarantines doc, leaves earlier steps intact.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(rag): 8-stage pipeline runner with failure isolation"
```

### Task G3: Stage 1 — Fetch

**Files:** `rag/pipeline/stages/fetch.py` — invokes `connector.fetch(sd)`; writes raw bytes to BlobStore at `kb/{kb_id}/raw/{content_hash}.bin`.
**Test:** mock connector returns 1MB blob → stored; content_hash deterministic; redirect on identical hash skips storage.

```bash
git commit -m "feat(rag): pipeline stage — fetch (to BlobStore + dedupe)"
```

### Task G4: Stage 2 — Extract

**Files:** `rag/pipeline/stages/extract.py` — mime-dispatch via extractor registry.
**Test:** PDF bytes → ExtractedDocument with text; unsupported mime → quarantine reason `no extractor for image/x-foo`.

```bash
git commit -m "feat(rag): pipeline stage — extract"
```

### Task G5: Stage 3 — Normalize

**Files:** `rag/pipeline/stages/normalize.py` — encoding to UTF-8, NFC unicode, language detect via `langdetect` (lazy), content-hash recompute.
**Test:** Latin-1 → UTF-8; language tag populated; duplicate hash within KB → mark `superseded`.

```bash
git commit -m "feat(rag): pipeline stage — normalize"
```

### Task G6: Stage 4 — Redact (PII via shared guardrail)

**Files:** `rag/pipeline/stages/redact.py` — calls Gateway's shared `guardrails.redact_pii(text, policy)` when KB's ingest policy enables PII redaction.
**Test:** doc with email + SSN → both replaced by `[REDACTED:EMAIL]` / `[REDACTED:SSN]`.

```bash
git commit -m "feat(rag): pipeline stage — redact (shared guardrail)"
```

### Task G7: Stage 5 — Chunk

**Files:** `rag/pipeline/stages/chunk.py` — resolves chunker per KB settings; emits chunks with `meta.heading_path`/`page`/`function` propagated.
**Test:** 5000-token doc with `chunker_id="fixed_token"` → ~10 chunks at default 512.

```bash
git commit -m "feat(rag): pipeline stage — chunk"
```

### Task G8: Stage 6 — Metadata enrich

**Files:** `rag/pipeline/stages/enrich.py` — title from doc/page1/url; author from doc meta; tags from KB defaults + connector hints; source URL canonicalised.
**Test:** PDF without title → falls back to filename; tags merged.

```bash
git commit -m "feat(rag): pipeline stage — metadata enrich"
```

### Task G9: Stage 7 — Embed (batched via Gateway)

**Files:** `rag/pipeline/stages/embed.py` — batches chunks (default 64) → `gateway.embed(texts, model=kb.embedder_id)`; usage emitted with unit `embeddings`.
**Test:** 200 chunks → 4 batched calls; on batch failure → retry once then quarantine doc.

```bash
git commit -m "feat(rag): pipeline stage — embed (batched, gateway-routed)"
```

### Task G10: Stage 8 — Index (vector + BM25 + ACL)

**Files:**
- `rag/pipeline/stages/index.py` — writes to: vector store (resolved per KB) + BM25 store (`kb_chunk_bm25` Postgres FTS) + ACL store
- Create: `rag/lexical/bm25_pg.py` — uses `tsvector`/`tsquery` + `rank-bm25` for cross-backend parity tests
- Test: `tests/rag/pipeline/test_stage_index.py`

- [ ] **Step 1: Failing test** — after stage runs, vector_store.count(ns=kb)+=N, BM25 row inserted per chunk, ACL row per chunk.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(rag): pipeline stage — index (vector + BM25 + ACL)"
```

### Task G11: Re-embed job (on embedder switch)

**Files:** `rag/pipeline/reembed.py` — when KB `embedder_id` changes, enqueue re-embed of all chunks (visible job).
**Test:** patch KB embedder → job created with one step per existing chunk; old vectors deleted on success.

```bash
git commit -m "feat(rag): re-embed job on embedder change"
```

---

## Phase H — ACL mirroring

### Task H1: ACLProvider protocol + mapper registry

**Files:**
- Create: `rag/acl/protocol.py`, `rag/acl/registry.py`
- Test: `tests/rag/acl/test_protocol.py`

```python
class AclProvider(Protocol):
    connector_kind: str
    async def map(self, source_acls: AclSet, org_id: str) -> ResolvedAcl: ...

@dataclass
class ResolvedAcl:
    user_ids: set[str]
    group_ids: set[str]
    public: bool
    unresolved: set[str]                # best-effort, kept for re-resolution
```

- [ ] **Step 1–6**: Implement, commit.

```bash
git commit -m "feat(rag): ACL provider protocol + registry"
```

### Task H2: IdP mapping (best-effort)

**Files:** `rag/acl/idp_mapper.py` — resolves connector-native user/group ids to org users/groups via Control Plane IdP mapping; unresolved kept for later.
**Test:** GDrive emails → Org users by email match; unknown email → in `unresolved`.

```bash
git commit -m "feat(rag): IdP mapping for ACLs (best-effort)"
```

### Task H3: ACL store + retrieval filter

**Files:**
- Create: `rag/acl/store.py` — denormalised per-chunk allow set + per-doc allow set; index on `(kb_id, user_id)` and `(kb_id, group_id)`
- Modify: `rag/search/` retrieval to inject `actor ∈ allow_set` filter server-side
- Test: `tests/rag/acl/test_filter.py`

- [ ] **Step 1: Failing test** — actor with no membership → 0 hits even if vector similar; actor in allowed group → hits returned.
- [ ] **Step 2–6**: Implement; commit.

```bash
git commit -m "feat(rag): ACL store + server-side retrieval filter"
```

### Task H4: ACL re-sync on source change

**Files:** `rag/acl/resync_worker.py` — listens for connector ACL-change webhooks (where supported) or scheduled re-sync.
**Test:** simulate ACL-change event → resync runs for affected docs only.

```bash
git commit -m "feat(rag): ACL re-sync worker"
```

### Task H5: Permission test endpoint + UI hook

**Files:** `POST /v1/kbs/{id}/permission-test` body `{user_id}` → returns doc count & sample doc ids the user could retrieve.
**Test:** seed 3 docs with disjoint ACLs; tests for 3 different users return distinct counts.

```bash
git commit -m "feat(rag): permission-test endpoint"
```

---

## Phase I — Search (hybrid + RRF + rerank)

### Task I1: BM25 lexical retrieval

**Files:** `rag/search/lexical.py` — Postgres FTS `to_tsquery(plainto_tsquery(...))` + `ts_rank_cd`; top-k.
**Test:** `tests/rag/search/test_lexical.py` — known terms rank above unrelated text.

```bash
git commit -m "feat(rag): BM25/FTS lexical retrieval"
```

### Task I2: Dense retrieval via vector store

**Files:** `rag/search/dense.py` — embed query via gateway, query vector store with filters.
**Test:** asserts dense hits for paraphrase of fixture chunk.

```bash
git commit -m "feat(rag): dense retrieval"
```

### Task I3: Hybrid + Reciprocal Rank Fusion

**Files:** `rag/search/hybrid.py` + `rag/search/rrf.py`
**Test:** lexical-only top result and dense-only top result both appear in fused top-3 with RRF k=60.

```python
# rag/search/rrf.py
def reciprocal_rank_fusion(*ranked_lists: list[str], k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for lst in ranked_lists:
        for rank, doc_id in enumerate(lst):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
```

```bash
git commit -m "feat(rag): hybrid retrieval with RRF"
```

### Task I4: Metadata filters + boosts

**Files:** `rag/search/filters.py` — source / language / date-range / tag / author; `rag/search/boosts.py` — freshness (decay), source priority weights, popularity from `kb_queries`.
**Test:** filter date-range excludes older doc; freshness boost surfaces newer chunk over older equally-similar one.

```bash
git commit -m "feat(rag): retrieval filters + boosts"
```

### Task I5: Rerank stage

**Files:** `rag/search/rerank.py` — calls `gateway.rerank(query, docs, model=settings.rerank_model)` (default `voyage-rerank`).
**Test:** mocks gateway rerank → returned order applied.

```bash
git commit -m "feat(rag): rerank via gateway"
```

### Task I6: Federated multi-KB search

**Files:** `rag/search/federated.py` — fans out to N KBs in parallel, merges with normalized scores, reranks globally.
**Test:** 3 KBs each return 5 hits → merged top-10 contains hits from all KBs proportionally.

```bash
git commit -m "feat(rag): federated multi-KB search"
```

### Task I7: Search router

**Files:** `POST /v1/kbs/{id}/search`, `POST /v1/kbs/federated/search`
**Test:** RBAC `kb:read`; ACL filter applied; pagination via cursor.

```bash
git commit -m "feat(rag): search REST endpoints"
```

---

## Phase J — Retrieval policies

### Task J1: Policy model + per-KB defaults

**Files:**
- Create: `rag/policies/model.py` (`RetrievalPolicy`)
- Migration: `retrieval_policies(id, kb_id|null=org-default, top_k, min_score, freshness_days, max_tokens_to_llm, source_weights_json, rerank_enabled)`
- Test: `tests/rag/policies/test_model.py`

- [ ] **Step 1–6**: Implement, commit.

```bash
git commit -m "feat(rag): retrieval policies model"
```

### Task J2: Resolution at query time + per-request override

**Files:** `rag/policies/resolver.py` — request → header `x-rag-policy-id` > KB default > org default.
**Test:** asserts top_k from header overrides KB default.

```bash
git commit -m "feat(rag): retrieval policy resolution + per-request override"
```

---

## Phase K — Search providers (external "AI search")

### Task K1: SearchProvider protocol + registry

**Files:**
- Create: `rag/search/providers/protocol.py`, `rag/search/providers/registry.py`
- Migration: `search_providers(id, org_id, kind, config_encrypted, enabled, default_for_web)`
- Test: `tests/rag/search/providers/test_protocol.py`

```python
class SearchProvider(Protocol):
    name: str
    async def search(self, query: str, opts: SearchOpts) -> SearchResults: ...

@dataclass
class SearchOpts:
    top_k: int = 10
    site_include: list[str] | None = None
    site_exclude: list[str] | None = None
    freshness_days: int | None = None
    safe_search: bool = True

@dataclass
class SearchResult:
    title: str; url: str; snippet: str; published_at: datetime | None; score: float | None
```

- [ ] **Step 1–6**: Implement, commit.

```bash
git commit -m "feat(rag): SearchProvider protocol + registry"
```

### Task K2: Tavily provider

**Files:** `rag/search/providers/tavily.py` — `tavily-python` async; respx-mocked.
**Test:** returns k results; advanced filters mapped.

```bash
git commit -m "feat(rag): Tavily search provider"
```

### Task K3: Exa provider

**Files:** `rag/search/providers/exa.py` — `exa-py`.
**Test:** semantic search variant; date filters.

```bash
git commit -m "feat(rag): Exa search provider"
```

### Task K4: Brave / Bing / Google CSE providers

**Files:** `rag/search/providers/brave.py`, `bing.py`, `google_cse.py` — each respx-mocked.
**Test:** one per provider asserting auth header + result mapping.

```bash
git commit -m "feat(rag): Brave + Bing + Google CSE search providers"
```

### Task K5: Internal (RAG) as a SearchProvider

**Files:** `rag/search/providers/internal.py` — wraps `federated_search` to expose the same protocol.
**Test:** identical interface; results carry `meta["kb_id"]`.

```bash
git commit -m "feat(rag): internal-KBs search provider"
```

### Task K6: /v1/search public endpoint

**Files:** router that resolves `provider_id` → SearchProvider; falls back to internal when configured.
**Test:** RBAC + per-org enablement; fallback path covered.

```bash
git commit -m "feat(rag): /v1/search public endpoint + provider selection"
```

---

## Phase L — Answer generation (streaming + citations)

### Task L1: Answer service skeleton

**Files:**
- Modify: `rag/service.py` — `async def answer(query, kb_ids, actor, opts) -> AsyncIterator[AnswerEvent]`
- Create: `rag/answer/types.py` — `AnswerEvent = TokenEvent | CitationEvent | FinalEvent | ErrorEvent`
- Test: `tests/rag/answer/test_service.py`

- [ ] **Step 1: Failing test** — given mocked retrieval + mocked `gateway.complete` streamer, service yields TokenEvents then a FinalEvent with citations resolved.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(rag): answer service skeleton with citation events"
```

### Task L2: Citation marker injection + resolution

**Files:** `rag/answer/citations.py`
**Test:** model emits `[1]` / `[2]` mid-stream → CitationEvent fired with `{n: 1, doc_id, chunk_id, permalink}` resolved at first occurrence.

```python
# rag/answer/citations.py
CITATION_RE = re.compile(r"\[(\d+)\]")

class CitationTracker:
    def __init__(self, retrieved: list[Chunk]):
        self._retrieved = {i + 1: c for i, c in enumerate(retrieved)}
        self._emitted: set[int] = set()

    def scan(self, token: str) -> list[CitationEvent]:
        out = []
        for m in CITATION_RE.finditer(token):
            n = int(m.group(1))
            if n in self._emitted or n not in self._retrieved:
                continue
            chunk = self._retrieved[n]
            out.append(CitationEvent(n=n, doc_id=chunk.doc_id, chunk_id=chunk.id,
                                     permalink=chunk.meta.get("source_url"), snippet=chunk.text[:280]))
            self._emitted.add(n)
        return out
```

```bash
git commit -m "feat(rag): citation marker scan + event emission"
```

### Task L3: Multi-turn conversational RAG (question rewrite + summarisation)

**Files:** `rag/answer/conversational.py` — given prior turns, calls `gateway.complete` with a tiny prompt to rewrite question; summarises older turns when token budget exceeded.
**Test:** 5-turn conversation → rewritten query contains entity reference from turn 1; summarisation kicks in at 4kT.

```bash
git commit -m "feat(rag): multi-turn conversational rewrite + summary"
```

### Task L4: Refusal gate ("I don't know")

**Files:** `rag/answer/refusal.py` — if max retrieved score < `policy.min_score` or no chunks pass ACL → emit refusal FinalEvent.
**Test:** no hits → answer is "I don't have a confident source for that."; no LLM call made.

```bash
git commit -m "feat(rag): no-source refusal gate"
```

### Task L5: Configurable length / tone / language

**Files:** `rag/answer/style.py` — composes system prompt per opts; caveman-style instructions only.
**Test:** opts `tone="formal"` and `language="fr"` → outgoing system block reflects both.

```bash
git commit -m "feat(rag): configurable answer style (length, tone, language)"
```

### Task L6: Answer router (SSE)

**Files:** `POST /v1/kbs/{id}/answer`, `POST /v1/kbs/federated/answer` — SSE.
**Test:** httpx streaming client receives events in order; final event includes `usage` + `citations`.

```bash
git commit -m "feat(rag): SSE answer endpoint (single + federated)"
```

---

## Phase M — Eval framework

### Task M1: Test set + run model

**Files:**
- Modify: `knowledge_base/model.py` add `KbEval`, `KbEvalRun`
- Migration: `kb_evals(id, kb_id, name, test_set_json, judge_model, judge_temperature)`, `kb_eval_runs(id, eval_id, snapshot_id, metrics_json, ran_at)`
- Test: `tests/rag/eval/test_models.py`

```bash
git commit -m "feat(rag): eval + eval_runs tables"
```

### Task M2: Retrieval metrics (recall@k, MRR, nDCG)

**Files:** `rag/eval/retrieval_metrics.py`
**Test:** known relevance set → recall@5=0.6, MRR=0.5, nDCG monotonic with rank.

```python
# rag/eval/retrieval_metrics.py
def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant: return 0.0
    hits = sum(1 for d in retrieved[:k] if d in relevant)
    return hits / len(relevant)

def mrr(retrieved: list[str], relevant: set[str]) -> float:
    for i, d in enumerate(retrieved, start=1):
        if d in relevant:
            return 1.0 / i
    return 0.0

def ndcg_at_k(retrieved, relevance_grades: dict[str, int], k: int) -> float:
    import math
    dcg = sum((2 ** relevance_grades.get(d, 0) - 1) / math.log2(i + 2)
              for i, d in enumerate(retrieved[:k]))
    ideal = sorted(relevance_grades.values(), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0
```

```bash
git commit -m "feat(rag): retrieval metrics (recall@k, MRR, nDCG)"
```

### Task M3: Answer metrics (LLM-as-judge: correctness + faithfulness)

**Files:** `rag/eval/answer_judge.py` — routes through `gateway.complete` with disclosed judge model + temp.
**Test:** mocked judge returns `{"correctness": 0.8, "faithfulness": 0.9}` → metrics stored verbatim.

```bash
git commit -m "feat(rag): LLM-as-judge metrics with disclosed model/temp"
```

### Task M4: Eval runner

**Files:** `rag/eval/runner.py` — runs eval on KB snapshot id; persists `metrics_json`; compares vs previous run; emits regression webhook when drop > threshold.
**Test:** seed eval with 3 items; run twice with mocked retrieval producing degraded second run → `kb.eval.regression` webhook fires.

```bash
git commit -m "feat(rag): eval runner + regression detection"
```

### Task M5: Eval REST

**Files:** `GET/POST /v1/kbs/{id}/evals`, `POST /v1/kbs/{id}/evals/{eid}/run`, `GET /v1/kbs/{id}/eval-runs`.
**Test:** RBAC `kb:eval`; run is async (returns 202 + run id).

```bash
git commit -m "feat(rag): eval REST + async run"
```

---

## Phase N — Analytics

### Task N1: Query log + feedback

**Files:**
- Modify: `knowledge_base/model.py` add `KbQuery`, `KbFeedback`
- Migration: `kb_queries`, `kb_feedback` (per-citation thumbs / comment)
- Test: `tests/rag/analytics/test_query_log.py`

- [ ] **Step 1–6**: Implement, commit.

```bash
git commit -m "feat(rag): kb_queries + kb_feedback tables"
```

### Task N2: Analytics rollups + endpoints

**Files:** `rag/analytics/rollups.py` (hourly), `rag/analytics/router.py` — top queries, zero-result queries, citation hit-rate per doc, thumbs ratio.
**Test:** seed 100 query rows → rollup returns expected top-5 and zero-result list.

```bash
git commit -m "feat(rag): analytics rollups + endpoints"
```

### Task N3: Cost dashboard (tokens + storage + queries)

**Files:** `rag/analytics/cost.py` — joins `usage_events` (from Control Plane) on `module="rag"` + storage size from BlobStore + chunk count.
**Test:** seeded usage events + chunk count → endpoint returns three series.

```bash
git commit -m "feat(rag): cost dashboard endpoint"
```

---

## Phase O — Consumer surfaces & webhooks

### Task O1: KB webhook event types

**Files:** `rag/webhooks/event_types.py` — registers `kb.sync_complete`, `kb.sync_failed`, `kb.doc.indexed`, `kb.doc.quarantined`, `kb.answer.generated`, `kb.eval.regression` with Control Plane registry.
**Test:** registry contains all six after import.

```bash
git commit -m "feat(rag): webhook event-type registrations"
```

### Task O2: Chat module integration (KB attachment as conversation context)

**Files:** `rag/integrations/chat.py` — exposes `attach_kbs(conversation_id, kb_ids, policy_id)`; chat retrieves via `rag.retrieve(...)` before LLM call.
**Test:** chat turn with attached KB returns citations in stream.

```bash
git commit -m "feat(rag): chat module integration (KB attachment + citations)"
```

### Task O3: Internal facade

**Files:** `rag/__init__.py` exports `retrieve`, `answer`, `ingest_text`, `search_external`.
**Test:** `tests/rag/test_facade.py` — imports work; signatures stable.

```bash
git commit -m "feat(rag): internal facade for cross-module imports"
```

---

## Phase P — Playground

### Task P1: KB chat playground

**Files:**
- Create: `rag/playground/router.py`
- Migration: `kb_playground_sessions(id, kb_id, prompt, settings_json, created_at)`
- Test: `tests/rag/playground/test_router.py`

- [ ] **Step 1: Failing test** — POST creates a session that records KB(s) + policy + model + question; replays produce identical retrieved chunks (deterministic snapshot id captured); "save as eval test case" copies into `kb_evals.test_set_json`.
- [ ] **Step 2–6**: Implement, commit.

```bash
git commit -m "feat(rag): KB chat playground + save-as-eval"
```

---

## Phase Q — Frontend UI

### Task Q1..Qn: RAG pages

One task each (TanStack Router + React Query). Defer e2e per project rules.

- [ ] Q1: RAG → KBs list
- [ ] Q2: KB detail → Overview (status, stats)
- [ ] Q3: KB detail → Documents (table, filter, status badges, drill-in)
- [ ] Q4: KB detail → Connectors (configure + schedule + run history)
- [ ] Q5: KB detail → Settings (embedder, chunker, retrieval policy)
- [ ] Q6: KB detail → Permissions (ACL test, allow-list browser)
- [ ] Q7: KB detail → Chat / Playground (Monaco editor, retrieved-chunks pane)
- [ ] Q8: KB detail → Analytics (top queries, zero-result, citation hit-rate)
- [ ] Q9: KB detail → Evals (test-set CRUD + run launcher + results compare)
- [ ] Q10: Global → Search Providers config
- [ ] Q11: Global → Connector marketplace (preset templates per connector)
- [ ] Q12: KB detail → Quarantine (failed docs + retry)

Each: implement page + one component-level unit test for non-trivial logic.

```bash
git commit -m "feat(rag): UI <page>"
```

---

## Phase R — Sync operations polish

### Task R1: Cron scheduler

**Files:** `rag/connectors/scheduler.py` (extend) — parses cron, ticks at minute boundary, dispatches due connectors.
**Test:** scheduler tick with mocked clock → triggers connector whose `next_run <= now`.

```bash
git commit -m "feat(rag): connector cron scheduler"
```

### Task R2: 429 backoff + Retry-After honor

**Files:** `rag/connectors/backoff.py` — exponential backoff capped; honors `Retry-After` header.
**Test:** mocked 429 with `Retry-After: 12` → next attempt scheduled at +12s.

```bash
git commit -m "feat(rag): connector backoff + Retry-After"
```

### Task R3: Content-hash dedupe on full re-walk

**Files:** `rag/pipeline/dedupe.py` — when connector lacks delta, full re-walk uses content-hash to skip unchanged docs.
**Test:** second run with identical bytes → 0 new ingest jobs created.

```bash
git commit -m "feat(rag): content-hash dedupe on full re-walk"
```

---

## Final checks

- [ ] **Step F1: Run only touched-file unit tests**

For every file you modified, run `pytest <its test path> -x`. Do NOT run the full suite. Do NOT run E2E. E2E targets (create KB → upload → ask → see citation; web-crawler sample-site ingest; ACL block; eval pass/fail) are added by the orchestrator at the end across modules.

- [ ] **Step F2: Lint**

```bash
cd server/api && ruff check src/ai_portal/rag src/ai_portal/knowledge_base --fix
ruff format src/ai_portal/rag src/ai_portal/knowledge_base
```

- [ ] **Step F3: Type check**

```bash
mypy src/ai_portal/rag src/ai_portal/knowledge_base
```

- [ ] **Step F4: Migration round-trip**

```bash
alembic downgrade -1 && alembic upgrade head
```

- [ ] **Step F5: Type alignment check (Python ↔ TS)**

```bash
python server/api/scripts/check_types_align.py
```

- [ ] **Step F6: Hand off to orchestrator**

Report:
- All Phase A–R tasks completed: yes/no
- Number of commits on this worktree
- Any deferred items (with reason)
- DO NOT write E2E. DO NOT run E2E. Orchestrator runs E2E across all modules.

---

## Out of scope (deferred per spec)

- Layout-aware document parsing beyond what Unstructured / PyMuPDF provide (no LayoutLM-style models in pipeline)
- Multi-modal (image-as-query) retrieval — text queries only for v1
- Knowledge graph derived from docs (entity extraction → graph store)
- Web SDK / embeddable widget for public sites
- No-code KB sharing externally (public KBs)
- Fine-tuning embedders on org data
- On-device retrieval
- Real-time low-latency KB streaming (collaborative ingest)
- Versioned dataset releases for downstream training
- Cross-tenant KB sharing
- Custom embedding model upload UI (config-only via env / settings)
