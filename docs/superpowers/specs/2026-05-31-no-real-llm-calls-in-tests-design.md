# No Real LLM/External Calls in Tests (All Modules)

**Date:** 2026-05-31
**Status:** Approved (design)

## Problem

Tests can hit real, paid provider APIs (chat, embeddings, rerank, moderation,
agent loops, sandboxes). The live E2E backend (`e2e-up.sh`) booted with a real
`ANTHROPIC_API_KEY` and several E2E chat sends were un-mocked, so they called
Anthropic for real — cost + flakiness.

## Goal

No test — unit, integration, smoke, or E2E, backend or frontend — ever makes a
real paid external call. **One app mode.** No test/prod runtime flag, no
provider doubles baked into `src/`. Production is unchanged.

## Approach — mock at the natural injection point, plus a backstop

Tests already own their dependencies; they mock the LLM where they inject it. No
`src/` changes.

### Backend — boundary mocks + one network tripwire

- Keep existing boundary mocks: provider adapters via `respx` (httpx layer);
  chat streaming via the `patched_fake_provider` monkeypatch fixture; module
  suites monkeypatch their own resolver/embedder.
- **Network tripwire** (`server/api/tests/conftest.py`, autouse): patches
  `socket.getaddrinfo` to raise for real provider hosts (`api.openai.com`,
  `api.anthropic.com`, `api.voyageai.com`, `api.cohere.com`,
  `generativelanguage.googleapis.com`). A test that forgets to mock fails loud
  instead of spending. Test-only — `src/` never sees it, so the app stays
  single-mode.

### Frontend E2E — browser mocks, shared helpers

- Shared `page.route` helpers in `apps/frontend/e2e/support/`:
  `chat-mock.ts` (`installChatStreamMock(page, { script, delayMs })` — SSE stream
  + `GET messages`; `delayMs` keeps the stream pending for the Stop-button
  tests), plus `rag-mock.ts`, `workers-mock.ts`, `memories-mock.ts`.
- `fixtures.ts`: extends Playwright `test` with a default catch-all chat-stream
  mock so every chat/agent spec is mocked unless it overrides — no spec leaks.
- Specs refactored onto the helpers (behavior identical); the 4 previously-leaky
  `chat-send.spec.ts` tests (Stop visible, Stop halts, input cleared,
  conversation-appears-in-sidebar) now mock; stale "requires ANTHROPIC_API_KEY"
  headers fixed.

### Live E2E server — keyless

- `scripts/e2e-up.sh` strips provider keys (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`
  / `GEMINI_API_KEY` / `VOYAGE_API_KEY` / `COHERE_API_KEY`) from the uvicorn +
  seed steps. The frontend mocks every provider response in the browser, so the
  real adapters are never invoked; with no key, anything un-mocked fails loud
  ($0). No special flag. Catalog seed uses `--skip-model-validation`, so
  model-select still populates.

## Verification

1. Backend unit/integration: `python -m pytest` (tripwire active; mocked tests
   stay green, adapter `respx` tests stay green).
2. Bring up the keyless E2E backend (`e2e-up.sh`), then `pnpm test:e2e`.
