# Design v2 — Vortex Migration

**Date:** 2026-04-19
**Worktree:** `design-v2`
**Status:** Design (pending implementation plan)

## Context

Migrate the existing frontend to the "Vortex" design system delivered by Claude Design as two handoff bundles:

- **Vortex.html** (6-screen enterprise portal: chat, kb, memories, models, keys, governance). Source: `https://api.anthropic.com/v1/design/h/2k5J7zcC4_Hhn7YERzjMvQ?open_file=Vortex.html`
- **Landing.html + Auth.html** (public landing + auth split-screen). Source: `https://api.anthropic.com/v1/design/h/nA9DUzzQe4-zVLfgq2QTNg?open_file=Landing.html`

Bundles are extracted at the worktree root as `.design-bundle-vortex/` and `.design-bundle-landing/` (gitignored; reference only).

**Scope rule:** Migrate only features that already exist in the current codebase. Features where the design exists but the feature does not (Models catalog, API keys) are deferred.

## Goals

- Pixel-faithful adoption of the Vortex visual language across all existing screens.
- Structural layout changes where the prototype layout differs materially from current (chat 3-col grid, KB master/detail, auth split-screen).
- Existing data layer, routes, and API contracts unchanged.
- Existing E2E suite stays green throughout.

## Non-Goals

- Models catalog screen and API keys screen (no backing code yet).
- Tweaks panel (theme/accent/density picker) — defer.
- Landing.html structural rewrite for `/` — tracked by separate spec `2026-04-15-vortex-landing-page-design.md`; this migration aligns tokens only.
- Backend changes of any kind. UI-only migration.

## Target Screens

| Route | Current component(s) | Vortex source | Change type |
|---|---|---|---|
| app shell | `AppShell`, `AppSidebar`, `MobileAppShell`, `MobileHeader`, `BottomTabBar`, `ConversationDrawer` | `Vortex.html` chrome | Structural + tokens |
| `/chat`, `/chat/conversations/*` | `ConversationThreadPage`, `ConversationsSidebarPanel`, `ChatComposerDock`, `ThreadItemChip` | `screen_chat.jsx` (3-col) | Structural + tokens |
| `/knowledge-bases`, `/knowledge-bases/$id` | `KnowledgeBases*` | `screen_kb.jsx` (master/detail) | Structural + tokens |
| `/memories` | `Memories*` | `screen_memories.jsx` (list/detail) | Structural + tokens |
| `/org/settings` | `RbacPolicyPanel`, `AuditLogPanel`, `RetentionPanel`, `UsagePanel` | `screen_gov.jsx` (tabbed gov-grid) | Structural + tokens |
| `/login`, `/register`, `/setup` | auth routes | `Auth.html` (split-screen) | Structural + tokens |
| `/` | `home/*` | `Landing.html` | Tokens only (structural defer) |
| 404, loading shells, error boundaries | `DefaultCatchBoundary`, `NotFound` | n/a | Tokens only |

Deferred (design exists, code does not):
- Models catalog screen
- API keys screen

## Design System

### Tokens & Theming

Global only — tokens, theming, fonts, resets:

- Copy Vortex's `:root`, `[data-theme="light"]`, `[data-theme="dark"]` CSS variable blocks verbatim into `frontend/src/app.css`. OKLCH palette (`--bg`, `--ink*`, `--panel`, `--line*`, `--accent`, `--ok`, `--warn`, `--err`, `--hl`, `--radius`, `--shadow-*`).
- Load IBM Plex Sans / Mono / Serif via `<link>` in `index.html`.
- ThemeContext writes `data-theme="light|dark"` and `data-density="compact|comfortable"` on `<html>` (replace current `dark` class approach).
- Extend `frontend/tailwind.config.ts` so utility classes reference the CSS variables:
  ```ts
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)', 'bg-2': 'var(--bg-2)', panel: 'var(--panel)',
        line: 'var(--line)', 'line-2': 'var(--line-2)',
        ink: 'var(--ink)', 'ink-2': 'var(--ink-2)', 'ink-3': 'var(--ink-3)', 'ink-4': 'var(--ink-4)',
        accent: 'var(--accent)', 'accent-ink': 'var(--accent-ink)',
        ok: 'var(--ok)', warn: 'var(--warn)', err: 'var(--err)',
        hl: 'var(--hl)',
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
        serif: ['"IBM Plex Serif"', 'Georgia', 'serif'],
      },
      borderRadius: { DEFAULT: '4px', lg: '6px' },
    },
  }
  ```

### Styling preference order

1. **Tailwind utilities inline** — first choice for spacing, color, typography, simple layout, using tokens via Tailwind config.
2. **Global design-system classes** in `app.css` under `@layer components` — for patterns reused across screens: `.btn`, `.btn-primary`, `.btn-ghost`, `.pill`, `.pill-ok/warn/err/accent`, `.panel`, `.panel-head`, `.panel-body`, `.tbl`, `.kpi`, `.kpi-row`, `.brand-mark`, `.topbar-chip`, `.side-item`, `.side-label`, `.avatar`, `.filter-chip`, `.tabs`, `.tab`, `.prov`, `.prov-mark`, `.mono`, `.serif`, `.chat-grid`, `.chat-grid-2col`, `.conv-row`, `.msg`, `.msg-user`, `.msg-asst`, `.attach-chip`, `.compose-box`, `.model-chip`, `.mem-banner`, `.policy-row`, `.audit-row`, `.switch`, `.chart`, `.kv`, `.trace-tree`, plus keyframes (`vx-pulse`, `vx-bounce`, `vx-blink`, `vx-spin`). Copy from Vortex prototype verbatim.
3. **CSS Modules only when required** — only for a component with genuinely unique structural CSS that can't be expressed with utilities or system classes. Do not create per-component `.module.css` files by default.

## Migration Plan (execution order)

Each step is independently shippable. Run `pnpm test:e2e:filter <area>` after each; full `pnpm test:e2e` before merging the worktree.

### Step 1 — Tokens & global system

- Add IBM Plex link tags to `index.html`.
- Copy Vortex `:root` / theme blocks into `app.css`. Add `@layer components` with the reusable classes listed above.
- Extend `tailwind.config.ts` as specified.
- Switch ThemeContext from `dark` class to `data-theme` + `data-density` attributes.
- App renders with new tokens but old structural shells.

### Step 2 — App shell

Files: `frontend/src/components/layout/AppShell.tsx`, `AppSidebar.tsx`, `AppTopbar.tsx` (new — extracts the topbar concern from `AppShell`), `MobileAppShell.tsx`, `MobileHeader.tsx`, `BottomTabBar.tsx`, `ConversationDrawer.tsx`. `ConversationDrawer` is no longer used on desktop (its conversation-list role moves into the sidebar's `.side-section-convs`) but stays in place as the mobile slide-in drawer used by `MobileAppShell`.

- **Grid:** 220px sidebar + 1fr main; 44px topbar row on top.
- **Topbar:** brand block (220px, matches sidebar width), `.topbar-search` (Cmd-K), `.topbar-right` with health chip + theme toggle + avatar.
- **Sidebar:** `.side-section` nav (Chat, Knowledge, Memories, Org Settings), `.side-section-convs` inline conversation list (replaces standalone `ConversationsSidebarPanel` component but preserves its query hooks), `.sidebar-foot` org card.
- **Mobile:** keep existing responsive split (`MobileAppShell`, `MobileHeader`, `BottomTabBar`); apply Vortex tokens only.

### Step 3 — Auth pages

Files: `frontend/src/routes/login.tsx`, `register.tsx`, `setup.tsx`. Add shared `AuthShell.tsx` and `AuthFormCard.tsx` under `frontend/src/components/auth/`.

- Desktop split: hero aside (~50%) + form side. Mobile: hero collapses to compact header, form full-width below.
- Hero: `.brand-mark`, product name, tagline, decorative rays element, footer line. `--bg-2` background.
- Form card: centered on `--panel`, max-width ~360px. Header (h1 + subtitle), stacked fields, primary button, optional divider + SSO/OAuth (only providers exposed by backend), footer link.
- Per-page content (copy, field set): Login (email+password, remember, forgot), Register (name+email+password+confirm), Setup (workspace name, admin email, bootstrap token).
- Preserve existing form behavior, mutations, validation, redirects, error toasts.

### Step 4 — Chat screen

Files: `frontend/src/routes/chat/**`, `frontend/src/components/chat/ConversationThreadPage.tsx`, `ConversationsSidebarPanel.tsx`, `ChatComposerDock.tsx`, `ChatComposerDockMobile.tsx`, `ThreadItemChip.tsx`. Add `ConversationInspectorPanel.tsx` (new).

- **Grid desktop:** `.chat-grid` = `280px 1fr 320px`. Inspector toggleable; hidden → `.chat-grid-2col` = `280px 1fr`.
- **Column 1 — Conversation list:** `.conv-list` with search header, grouped rows (Today/Yesterday/Earlier) driven by existing `useConversationsListQuery`. Each `.conv-row` shows title, `.when` timestamp, 2-line preview, capability tag chips, unread dot. Active = `--hl` bg + accent inset shadow.
- **Column 2 — Thread:** `.chat-main` with `.chat-head` (title, `.model-chip`, breadcrumb, action buttons including inspector toggle), `.thread-scroll` with `.msg-user` / `.msg-asst`, `.attach-list`, `.msg-actions`, `.mem-banner` for memory hits, IBM Plex Serif blockquotes, mono code blocks. Streaming/thinking states via `vx-pulse` / `vx-bounce` keyframes. `ThreadItemChip` restyled to `.cap-tag`.
- **Column 2 — Composer:** `.compose-box` dock — textarea, model picker, capability toggles (Reflection, Research), send button.
- **Column 3 — Inspector (new):** right panel with message metadata — model, tokens, tool calls, retrieval hits, capability traces. Render whatever the current API exposes; placeholder (`<div>` with `TODO` comment) for sections without data. Hidden by default; toggle from `.chat-head-actions`.
- **Mobile:** single-column thread; column 1 opens via existing `MobileAppShell` drawer. Inspector hidden on mobile (defer).
- **Tail-query and streaming logic (`useConversationMessagesTailQuery`, `streaming_service`) unchanged.**

### Step 5 — Knowledge bases

Files: `frontend/src/routes/knowledge-bases/*.tsx`, `frontend/src/components/knowledge-bases/*`.

- **Index:** `.kpi-row` strip (KBs total, docs ingested, recent retrievals), `.tbl` listing with Name / Docs / Updated / Status (`.pill-ok`/`.pill-warn`) / Provider (`.prov` + `.prov-mark`).
- **Detail (`$id.tsx`):** 2-col — left `.run-list` (docs / sources / ingestion runs), right `.run-main` + `.run-inspect` (doc preview / chunk inspector). Upload + connector flows preserved, restyled.

### Step 6 — Memories

Files: `frontend/src/routes/memories.tsx`, `frontend/src/components/memories/*`.

- List with `.filter-bar` chips (type: user/feedback/project/reference). Each row shows content preview, type pill, source conversation link, `.ts` timestamp.
- Right-side detail panel (desktop) / modal (mobile): full content, edit/delete, last-used metadata.
- Existing CRUD endpoints unchanged.

### Step 7 — Org settings (Governance)

Files: `frontend/src/routes/org/settings.tsx`, `frontend/src/components/admin/*`.

- Tabbed layout using `.tabs` + `.gov-grid`.
- `RbacPolicyPanel` → `.policy-row` with `.switch`, scope chips, role grid.
- `AuditLogPanel` → `.audit-row` table with action / actor / target / timestamp / mono trace ID.
- `RetentionPanel` → `.panel` form rows, KPI header.
- `UsagePanel` → `.kpi-row` + `.chart` placeholder (existing chart recolored to accent tokens).

### Step 8 — Home, 404, loading shells

- Token-only restyle of home (`/`) — Landing.html structural migration tracked by `2026-04-15-vortex-landing-page-design.md`.
- `DefaultCatchBoundary`, `NotFound`, loading fallbacks: swap to tokenized surfaces.

## Docs & CLAUDE.md

Add **Design v2 Migration** section to root `CLAUDE.md`:
- Pointer to this spec.
- Bundle paths (`.design-bundle-vortex/`, `.design-bundle-landing/`).
- Rule: every migrated screen must keep existing E2E tests green — this is a visual/layout migration, not a behavior change.
- Rule: new styling follows preference order — Tailwind utilities → global design-system classes → CSS modules only when required.
- Rule: new components consume tokens via Tailwind (`bg-bg`, `text-ink-2`, etc.); never hardcode hex or oklch outside `app.css`.

Also refresh CLAUDE.md where stale; show diff before committing.

`.gitignore` additions: `.design-bundle-vortex/`, `.design-bundle-landing/`.

## Testing & Completion

- Existing Playwright suite stays green throughout. E2E backend port 8001; dev port 8000.
- Selector updates land in the same commit as component changes. Helpers (`createOrFindConversation`, `createOrFindKb`) keep their signatures.
- New visual surfaces (Auth split layout, sidebar conv list, chat inspector toggle) get new specs: render check, primary action, mobile collapse (min).
- Per-step: `pnpm test:e2e:filter <area>`; before merging the worktree: `pnpm test:e2e` (8 workers, 0 retries).
- Visual review against `Vortex.html` and `Auth.html` per screen.

## Risks & Mitigations

- **Selector churn breaks many tests at once** → migrate one screen per commit; update its tests in the same commit.
- **OKLCH browser support** — all modern Chromium/Firefox/Safari OK; no IE/legacy targets for this app.
- **Inspector column without data** → explicit placeholders with TODO comments; do not silently hide sections.
- **IBM Plex load flash** → `font-display: swap` via Google Fonts default; preconnect tags copied from Vortex.
- **Density mode interaction with existing spacing** → density attribute scopes spacing overrides in the global stylesheet; components read tokens only.

## Deferred (tracked, not in this spec)

- Models catalog screen (`screen_models.jsx` source; no current code).
- API keys screen (`screen_keys.jsx` source; no current code).
- Tweaks panel (theme/accent/density picker).
- Landing.html structural rewrite for `/` — separate spec.
- Chat inspector data backfill for tool-call traces and retrieval hits beyond what the current API exposes.
