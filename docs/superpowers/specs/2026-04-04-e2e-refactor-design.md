# E2E test refactor — design (2026-04-04)

## Scope

- **Implementation is limited to the feature git worktree** used for this effort (the checkout under `.worktrees/chat-remaining-features/`, not the default repo root working tree), until that branch is merged.
- All paths (`frontend/e2e/`, `playwright.config.ts`, root scripts) are relative to the **worktree** root that corresponds to that branch.
- This document may live on `main` for planning; **do not** mirror the refactor into the primary working tree unless merging.

## Goals

- Group Playwright specs **by product aspect** under `frontend/e2e/`, with a fourth area for **shell / navigation / home** (not only chat thread vs KB vs memories).
- Provide **one primary command** from the **repository root** that brings up the E2E stack (database, Redis, migrations, catalog seed, API, ingest worker where applicable) and runs the full Playwright suite.
- **Remove redundant** journeys; keep tests **short** and anchored to **real user-visible outcomes**.
- Centralize repetition in **helpers**; allow **topic-local helpers** to be imported across topics when that avoids duplication.

## Non-goals

- Rewriting production code solely to suit tests (small `data-testid` additions remain acceptable when aligned with existing patterns).
- Changing CI provider or replacing Playwright.

## Bounded contexts and directory layout

Playwright keeps `testDir: 'e2e'` (see `frontend/playwright.config.ts`). Specs move into subfolders; discovery continues to work.

| Folder | Aspect | Representative behaviors |
|--------|--------|---------------------------|
| `e2e/shell/` | Global chrome, navigation, home, conversation list | Sidebar / thread list, empty state and starters, capabilities entry points, home cards that are not “on” the memories or KB page |
| `e2e/chat/` | Active conversation: thread, composer, send/stream, model, KB in composer, RAG/stream UI | Send message, KB picker attach/detach, indicators, tool-call / “searching KB” stream |
| `e2e/kb/` | Knowledge bases list, detail, uploads, ingest lifecycle | Create KB, upload, progress → `ready`, limits / oversize |
| `e2e/memories/` | Memories page journeys | CRUD, pause/resume, badges |

**Placement rule:** The folder matches the **surface whose behavior is primarily asserted**. Example: a flow that starts on home but asserts the memories editor belongs under `memories/` if the contract under test is memories behavior; if the contract is “home card navigates correctly,” it can live under `shell/`. When ambiguous, prefer the **assertion target** over the entry route.

**Global files** remain at `e2e/global-setup.ts` and `e2e/global-teardown.ts` with config paths unchanged.

## Helpers and imports

- **`e2e/support/`** (rename from `e2e/helpers/` in implementation, or keep one canonical name—implementer picks one and updates imports): shared building blocks only—API clients, auth/dev token usage, stable locator factories, waits (`networkidle` where required), factories (conversation, KB), and cross-topic flows used **twice or more**.
- **`e2e/<topic>/helpers.ts`** (or `e2e/<topic>/support.ts`): optional, for flows **mostly** used in that topic.
- **Cross-topic imports are allowed:** a `chat/` spec may import from `kb/helpers.ts` (or `support/`) when a journey genuinely spans aspects and duplicating steps would be worse than a directed import. Prefer **`support/`** when a helper is clearly shared; keep topic files for KB-specific or chat-specific sequencing that another topic happens to reuse once.

Specs should read as: arrange (support) → act → assert one or two **user-visible** outcomes; avoid duplicate “same journey, different file” unless cost or env requirements differ (e.g. live LLM vs UI-only).

## Root orchestration

The repo currently has **no root `package.json`**. Add a **minimal** root manifest (or a single script only—implementer may choose `package.json` for discoverability) with one script, e.g. `test:e2e`, that:

1. Starts or assumes the E2E stack using the same semantics as `scripts/e2e-up.sh` (Docker Postgres/Redis, migrations, catalog seed, API on the dedicated port, RQ ingest worker, env vars documented in `frontend/e2e/README.md`).
2. Runs `pnpm --dir frontend test:e2e` so Playwright still owns **Vite** via `webServer` in `playwright.config.ts`.

**Windows:** document **Git Bash or WSL** for the bash entry point, or add a thin `scripts/e2e-all.ps1` that invokes equivalent steps—implementation plan should pick one and keep README accurate.

## De-duplication principles

- **One canonical spec per user-visible contract** (e.g. single strong ingest-to-ready path; single KB picker attach persistence path unless one test is “cheap UI” and another requires embeddings).
- Merge files that differ only in timing/copy-paste; split when **env cost** or **flakiness profile** differs (document in README table).
- Update **`frontend/e2e/README.md`** to a single matrix: folder → spec file → behavior → required keys/services.

## Playwright configuration

- No requirement to change `workers` or parallelism as part of this refactor; moving files does not require `testDir` changes.
- `globalSetup` / `globalTeardown` paths stay `./e2e/global-setup.ts` and `./e2e/global-teardown.ts`.

## Acceptance criteria

- All previous behaviors covered by the pre-refactor suite remain covered **or** explicitly dropped with rationale in the README (no silent loss).
- `pnpm test:e2e` from `frontend/` still works for developers who already ran `e2e-up.sh`.
- Root `test:e2e` (or equivalent) runs full stack + Playwright on a clean machine following README.
- Spec count and line noise trend **down** after redundant merges.

## Self-review (spec quality)

- **Placeholders:** None; ambiguous placement uses the assertion-target rule above.
- **Consistency:** Shell vs chat vs kb vs memories aligns with agreed option B (dedicated shell) and aspect/topic grouping.
- **Scope:** Refactor + orchestration + helpers; no backend feature work.
- **Ambiguity:** Cross-topic helper imports are explicitly allowed; preference order is `support/` first, then topic helper, then duplicate.

---

**Next step:** Review this document. After approval, use the **writing-plans** skill to produce an implementation plan (file moves, helper extraction list, root script shape, README updates, CI touchpoints if any).
