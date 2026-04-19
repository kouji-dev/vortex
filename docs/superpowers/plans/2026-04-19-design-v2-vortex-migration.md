# Design v2 Vortex Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the existing frontend to the Vortex design system (chat-first enterprise portal) and the Auth split-screen pattern, applying tokens via CSS variables consumed through Tailwind v4, with global design-system classes for reusable patterns.

**Architecture:** Three-layer styling: (1) CSS variables in `app.css` define OKLCH tokens with `data-theme` and `data-density` attribute selectors; (2) Tailwind v4 `@theme` block exposes those tokens as utility classes; (3) global `@layer components` block holds reusable design-system classes. CSS modules only when component-unique structural rules can't be expressed otherwise. Behavior, routes, and data layer untouched — UI-only migration.

**Tech Stack:** React 19, TanStack Router, TanStack Query, Tailwind v4 (CSS-config), TypeScript, Playwright (E2E), Vite 8.

**Spec:** `docs/superpowers/specs/2026-04-19-design-v2-vortex-migration.md`

**Reference bundles** (gitignored, in worktree root after Task 0):
- `.design-bundle-vortex/project/Vortex.html` + `src/*.jsx` + `styles.css`
- `.design-bundle-landing/project/Auth.html` + `Landing.html`

---

## File Map

### New files
- `frontend/src/components/layout/AppTopbar.tsx` — Topbar (extracts header concern from `AppShell`)
- `frontend/src/components/chat/ConversationInspectorPanel.tsx` — right-column message inspector
- `frontend/src/components/auth/AuthShell.tsx` — split-screen wrapper (hero + form)
- `frontend/src/components/auth/AuthFormCard.tsx` — shared form card (header + fields + footer)

### Modified files (visual / structural; no behavior change)
- `frontend/src/styles/app.css` — tokens, `@theme`, design-system `@layer components`
- `frontend/src/router.tsx` or wherever `<head>` is composed — add IBM Plex `<link>` tags
- `frontend/src/hooks/useIsMobile.ts` — write `data-density` attribute alongside `compact` class
- `frontend/src/components/layout/AppShell.tsx` — Vortex grid (220 + 1fr / 44 + 1fr)
- `frontend/src/components/layout/AppSidebar.tsx` — `.side-section` + `.side-section-convs`
- `frontend/src/components/layout/MobileAppShell.tsx`, `MobileHeader.tsx`, `BottomTabBar.tsx`, `ConversationDrawer.tsx` — token sweep
- `frontend/src/components/chat/ConversationThreadPage.tsx`, `ChatComposerDock.tsx`, `ChatComposerDockMobile.tsx`, `ConversationsRouteLayout.tsx`, `ConversationsSidebarPanel.tsx`, `ThreadItemChip.tsx`, `MarkdownMessage.tsx` — Vortex chat structure
- `frontend/src/routes/knowledge-bases/index.tsx`, `$id.tsx`, `frontend/src/components/knowledge-bases/*` — KB master/detail
- `frontend/src/components/memories/MemoriesPage.tsx`, `frontend/src/routes/memories.tsx` — list/detail
- `frontend/src/routes/org/settings.tsx`, `frontend/src/components/admin/{AuditLogPanel,RbacPolicyPanel,RetentionPanel,UsagePanel}.tsx` — `.gov-grid` / `.policy-row` / `.audit-row`
- `frontend/src/routes/login.tsx`, `register.tsx`, `setup.tsx` — wrap in `AuthShell` + `AuthFormCard`
- `frontend/src/components/home/*`, `frontend/src/routes/index.tsx` — token-only sweep
- `frontend/src/components/{DefaultCatchBoundary,NotFound}.tsx` — token-only sweep
- `CLAUDE.md` — Design v2 section
- `.gitignore` — `.design-bundle-*`

### E2E updates (selectors only; no behavior tests added unless noted)
- `frontend/e2e/auth/*.spec.ts` — selector update for new auth structure + new `auth-split-layout.spec.ts` (render check, mobile collapse)
- `frontend/e2e/chat/*.spec.ts` — selector update + new `chat-three-col-layout.spec.ts` (3-col render, inspector toggle, mobile drawer)
- `frontend/e2e/kb/*.spec.ts` — selector update
- `frontend/e2e/memories/*.spec.ts` — selector update
- `frontend/e2e/admin/*.spec.ts` — selector update
- `frontend/e2e/shell/*.spec.ts` — selector update for new topbar + sidebar
- `frontend/e2e/support/ui-helpers.ts` — internal selectors updated; external API (`createOrFindConversation`, `createOrFindKb`) unchanged

---

## Task 0: Worktree setup and reference bundles

**Files:**
- Run: `./scripts/worktree-up.sh design-v2`
- Modify: `.gitignore`
- Copy: bundles to worktree root

- [ ] **Step 0.1: Create worktree**

```bash
cd C:/Users/narut/Desktop/projects/ai-portal
./scripts/worktree-up.sh design-v2
```

Expected: creates `../ai-portal-design-v2` with isolated DBs/ports, writes `.worktree.env`. Idempotent if exists.

- [ ] **Step 0.2: Switch to worktree**

```bash
cd ../ai-portal-design-v2
git checkout -b design-v2
```

- [ ] **Step 0.3: Copy reference bundles into the worktree**

The bundles already live at `../ai-portal/.design-bundle-vortex` and `.design-bundle-landing`. Copy:

```bash
cp -r ../ai-portal/.design-bundle-vortex .
cp -r ../ai-portal/.design-bundle-landing .
ls .design-bundle-vortex/project/ .design-bundle-landing/project/
```

Expected: see `Vortex.html`, `styles.css`, `src/*.jsx` and `Auth.html`, `Landing.html`.

- [ ] **Step 0.4: Add to `.gitignore`**

Append to `.gitignore`:
```
.design-bundle-vortex/
.design-bundle-landing/
```

- [ ] **Step 0.5: Verify dev backend up on isolated worktree port**

```bash
cat .worktree.env  # confirm WORKTREE_NAME=design-v2 and unique ports
```

- [ ] **Step 0.6: Commit**

```bash
git add .gitignore
git commit -m "chore: design-v2 worktree — gitignore reference bundles"
```

---

## Task 1: Refresh root CLAUDE.md (Design v2 section)

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1.1: Append Design v2 section**

Add this section between `## E2E Test Principles` and `## Worktree Isolation`:

```markdown
## Design v2 (Vortex) Migration

In progress on `design-v2` worktree. Spec: `docs/superpowers/specs/2026-04-19-design-v2-vortex-migration.md`. Plan: `docs/superpowers/plans/2026-04-19-design-v2-vortex-migration.md`.

Reference bundles (gitignored, kept in worktree root):
- `.design-bundle-vortex/project/Vortex.html` — 6-screen enterprise portal (chat / kb / memories / models / keys / governance)
- `.design-bundle-landing/project/Auth.html` — split-screen auth (login / register / setup)
- `.design-bundle-landing/project/Landing.html` — landing page

### Styling rules

1. Tailwind utility classes inline (first preference). Tokens via Tailwind v4 `@theme` block in `frontend/src/styles/app.css`.
2. Global design-system classes in `app.css` `@layer components` for patterns reused across screens (`.btn`, `.pill`, `.panel`, `.tbl`, `.kpi`, `.conv-row`, `.chat-grid`, etc.).
3. CSS modules only when a component has unique structural CSS that can't be expressed with utilities + system classes.

Never hardcode hex/oklch outside `app.css`. Never use the `dark` class — use `data-theme="light|dark"` and `data-density="compact|comfortable"` on `<html>`.

### Migration rule

Each migrated screen must keep existing E2E tests green. This is a visual/layout migration, not a behavior change. Selector updates land in the same commit as the component change. Helpers (`createOrFindConversation`, `createOrFindKb`) keep their external signatures.
```

- [ ] **Step 1.2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: design-v2 section in CLAUDE.md"
```

---

## Task 2: Tokens, theming, fonts (foundation)

**Files:**
- Modify: `frontend/src/styles/app.css`
- Modify: `frontend/src/router.tsx` (head shell — add IBM Plex link tags)
- Modify: `frontend/src/hooks/useIsMobile.ts` (write `data-density`)
- Test: visual smoke only — no spec yet, since rendering with old structures still works.

- [ ] **Step 2.1: Add IBM Plex fonts to head shell**

Find where `<head>` is composed for SSR. In TanStack Start projects this is usually `__root.tsx` or the route shell. Locate via:

```bash
grep -rn "head:" frontend/src/routes/__root.tsx frontend/src/router.tsx 2>/dev/null | head -5
```

Add to the head links/scripts array (preserve existing entries):

```ts
{ rel: 'preconnect', href: 'https://fonts.googleapis.com' },
{ rel: 'preconnect', href: 'https://fonts.gstatic.com', crossOrigin: '' },
{ rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Serif:wght@500;600&display=swap' },
```

- [ ] **Step 2.2: Replace `app.css` with token foundation + design-system layer**

Open `.design-bundle-vortex/project/Vortex.html` and copy the `:root`, `[data-theme="light"]`, `[data-theme="dark"]`, reset, and shared component CSS blocks (lines ~10–1050 of the `<style>` block). Adapt into `frontend/src/styles/app.css`:

```css
@import 'tailwindcss' source('../');

/* ─── Vortex design tokens ─────────────────────────────────────────────── */
:root {
  --font-sans: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'IBM Plex Mono', ui-monospace, Menlo, monospace;
  --font-serif: 'IBM Plex Serif', Georgia, serif;

  --l-bg: oklch(98.8% 0.003 240);
  --l-bg-2: oklch(97.2% 0.004 240);
  --l-panel: oklch(100% 0 0);
  --l-line: oklch(91% 0.005 240);
  --l-line-2: oklch(94% 0.004 240);
  --l-ink: oklch(18% 0.01 240);
  --l-ink-2: oklch(38% 0.01 240);
  --l-ink-3: oklch(58% 0.008 240);
  --l-ink-4: oklch(72% 0.006 240);

  --d-bg: oklch(16% 0.008 240);
  --d-bg-2: oklch(19% 0.008 240);
  --d-panel: oklch(21% 0.008 240);
  --d-line: oklch(28% 0.008 240);
  --d-line-2: oklch(25% 0.008 240);
  --d-ink: oklch(96% 0.004 240);
  --d-ink-2: oklch(78% 0.006 240);
  --d-ink-3: oklch(62% 0.008 240);
  --d-ink-4: oklch(48% 0.008 240);

  --acc-cyan: oklch(62% 0.16 230);
  --acc-cyan-d: oklch(70% 0.14 230);
  --acc-violet: oklch(62% 0.16 290);
  --acc-lime: oklch(62% 0.16 140);

  --ok: oklch(64% 0.14 150);
  --warn: oklch(72% 0.15 75);
  --err: oklch(60% 0.2 25);

  --radius: 4px;
  --radius-lg: 6px;
}

[data-theme='light'] {
  --bg: var(--l-bg); --bg-2: var(--l-bg-2); --panel: var(--l-panel);
  --line: var(--l-line); --line-2: var(--l-line-2);
  --ink: var(--l-ink); --ink-2: var(--l-ink-2); --ink-3: var(--l-ink-3); --ink-4: var(--l-ink-4);
  --accent: var(--acc-cyan);
  --accent-ink: #fff;
  --shadow-sm: 0 1px 0 rgba(20,30,50,0.04);
  --shadow-md: 0 1px 2px rgba(20,30,50,0.05), 0 4px 12px rgba(20,30,50,0.04);
  --hl: rgba(20,80,180,0.06);
}

[data-theme='dark'] {
  --bg: var(--d-bg); --bg-2: var(--d-bg-2); --panel: var(--d-panel);
  --line: var(--d-line); --line-2: var(--d-line-2);
  --ink: var(--d-ink); --ink-2: var(--d-ink-2); --ink-3: var(--d-ink-3); --ink-4: var(--d-ink-4);
  --accent: var(--acc-cyan-d);
  --accent-ink: oklch(10% 0.02 240);
  --shadow-sm: 0 1px 0 rgba(0,0,0,0.3);
  --shadow-md: 0 2px 4px rgba(0,0,0,0.3), 0 8px 20px rgba(0,0,0,0.25);
  --hl: rgba(120,200,255,0.08);
}

/* Default theme until ThemeContext writes data-theme. */
html:not([data-theme]) { color-scheme: light dark; }
html:not([data-theme]) {
  --bg: var(--l-bg); --bg-2: var(--l-bg-2); --panel: var(--l-panel);
  --line: var(--l-line); --line-2: var(--l-line-2);
  --ink: var(--l-ink); --ink-2: var(--l-ink-2); --ink-3: var(--l-ink-3); --ink-4: var(--l-ink-4);
  --accent: var(--acc-cyan); --accent-ink: #fff;
  --hl: rgba(20,80,180,0.06);
}
@media (prefers-color-scheme: dark) {
  html:not([data-theme]) {
    --bg: var(--d-bg); --bg-2: var(--d-bg-2); --panel: var(--d-panel);
    --line: var(--d-line); --line-2: var(--d-line-2);
    --ink: var(--d-ink); --ink-2: var(--d-ink-2); --ink-3: var(--d-ink-3); --ink-4: var(--d-ink-4);
    --accent: var(--acc-cyan-d); --accent-ink: oklch(10% 0.02 240);
    --hl: rgba(120,200,255,0.08);
  }
}

/* ─── Tailwind v4 theme ─────────────────────────────────────────────────── */
@theme {
  --font-sans: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'IBM Plex Mono', ui-monospace, Menlo, monospace;
  --font-serif: 'IBM Plex Serif', Georgia, serif;

  --color-bg: var(--bg);
  --color-bg-2: var(--bg-2);
  --color-panel: var(--panel);
  --color-line: var(--line);
  --color-line-2: var(--line-2);
  --color-ink: var(--ink);
  --color-ink-2: var(--ink-2);
  --color-ink-3: var(--ink-3);
  --color-ink-4: var(--ink-4);
  --color-accent: var(--accent);
  --color-accent-ink: var(--accent-ink);
  --color-ok: var(--ok);
  --color-warn: var(--warn);
  --color-err: var(--err);
  --color-hl: var(--hl);

  --radius: 4px;
  --radius-lg: 6px;
}

/* ─── Base ──────────────────────────────────────────────────────────────── */
@layer base {
  * { box-sizing: border-box; }
  *, ::after, ::before, ::backdrop, ::file-selector-button {
    border-color: var(--line);
  }
  html, body {
    margin: 0; padding: 0;
    font-family: var(--font-sans);
    font-size: 13px;
    line-height: 1.45;
    background: var(--bg);
    color: var(--ink);
    -webkit-font-smoothing: antialiased;
    font-feature-settings: 'cv11', 'ss01';
    height: 100dvh;
    max-height: 100dvh;
    overflow: hidden;
    overscroll-behavior-y: none;
  }
  button { font: inherit; color: inherit; background: none; border: 0; padding: 0; cursor: pointer; }
  a { color: inherit; text-decoration: none; }
  input, select, textarea { font: inherit; color: inherit; }

  .using-mouse * { outline: none !important; }

  /* scrollbars (preserved from previous app.css, retokenized) */
  * {
    scrollbar-width: thin;
    scrollbar-color: var(--ink-4) transparent;
  }
  *::-webkit-scrollbar { width: 4px; height: 4px; }
  *::-webkit-scrollbar-track { background: transparent; }
  *::-webkit-scrollbar-thumb { border-radius: 9999px; background-color: var(--ink-4); }
  *::-webkit-scrollbar-thumb:hover { background-color: var(--ink-3); }
}

/* ─── Density ───────────────────────────────────────────────────────────── */
@layer base {
  [data-density='compact'] {
    --spacing: 0.21875rem;
    --text-xs: 0.6875rem;
    --text-sm: 0.8125rem;
    --text-base: 0.9375rem;
    --text-lg: 1.0625rem;
  }
  /* Back-compat for existing useIsMobile classToggle until that hook is updated. */
  .compact {
    --spacing: 0.21875rem;
    --text-xs: 0.6875rem;
    --text-sm: 0.8125rem;
    --text-base: 0.9375rem;
    --text-lg: 1.0625rem;
  }
}

/* ─── Utility helpers ───────────────────────────────────────────────────── */
@layer utilities {
  .mono { font-family: var(--font-mono); font-size: 12px; }
  .serif { font-family: var(--font-serif); }
  .pb-safe { padding-bottom: env(safe-area-inset-bottom); }
  .stream-surface-breathe { animation: aip-stream-breathe 2.4s ease-in-out infinite; }
  .page-enter { animation: aip-page-enter 150ms ease-out both; }

  @keyframes aip-stream-breathe { 0%, 100% { opacity: 1; } 50% { opacity: 0.94; } }
  @keyframes aip-page-enter { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes vx-spin { to { transform: rotate(360deg); } }
  @keyframes vx-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.45; } }
  @keyframes vx-blink { 0%, 49% { opacity: 1; } 50%, 100% { opacity: 0; } }
  @keyframes vx-bounce { 0%, 80%, 100% { transform: translateY(0); opacity: .3; } 40% { transform: translateY(-3px); opacity: 1; } }
}

/* ─── Design-system components ──────────────────────────────────────────── */
/* Copy the body of these classes verbatim from .design-bundle-vortex/project/Vortex.html
   <style> block. Place each cluster behind @layer components so utilities can override.
   The class clusters to copy are listed in the spec under "Global design-system classes".
   Group them with comment headers so future devs know what each block belongs to. */

@layer components {
  /* shell: .app, .topbar, .brand, .brand-mark, .brand-name, .brand-env, .topbar-search,
     .topbar-right, .topbar-chip, .avatar */
  /* sidebar: .sidebar, .side-section, .side-label, .side-item, .side-icon, .sidebar-foot,
     .org-card, .side-section-convs, .side-label-row, .conv-mini-label, .conv-mini, .btn-xs */
  /* main: .main, .main-inner, .screen-head */
  /* buttons: .btn, .btn-primary, .btn-accent, .btn-ghost, .btn-sm */
  /* tabs/filters: .tabs, .tab, .filter-bar, .filter-chip */
  /* pills: .pill, .pill-ok, .pill-warn, .pill-err, .pill-accent */
  /* providers: .prov, .prov-mark (incl. .xai, .voyage extensions) */
  /* tables: .tbl */
  /* panels: .panel, .panel-head, .panel-body */
  /* kpis: .kpi-row, .kpi, .kpi-label, .kpi-value, .kpi-delta */
  /* agents: .agent-grid, .agent-card, .agent-list, .agent-row, .spark-svg */
  /* run inspector (used for KB detail): .run-grid, .run-list, .run-list-item, .run-main,
     .run-scroll, .run-msg, .run-compose, .compose-box, .compose-row, .run-inspect,
     .inspect-sec, .kv, .trace-tree, .trace-node */
  /* form bits: .form-row, .textarea, .select, .section-head, .check-grid, .check-item */
  /* preview: .preview-head, .preview-body, .summary-card */
  /* obs/charts: .obs-grid, .obs-full, .chart, .chart-legend, .legend-item, .trace-row, .trace-bar */
  /* gov: .gov-grid, .gov-wide, .policy-row, .switch, .audit-row */
  /* canvas: .canvas-head, .canvas-grid, .canvas-cell, .capsule */
  /* tweaks (deferred but copy classes for future): .tweaks-panel, .tweaks-head, .tweaks-body, .seg */

  /* chat-specific (from Vortex.html UI section, lines ~1052-1701): */
  /* .chat-grid, .chat-grid-2col */
  /* .conv-list, .conv-list-head, .conv-list-search, .conv-list-scroll, .conv-grp-label,
     .conv-row (and .conv-row.active, .conv-row .top, .conv-row .title, .conv-row .when,
     .conv-row .unread-dot, .conv-row .preview, .conv-row .meta, .conv-row .cap-tag) */
  /* .chat-main, .chat-head, .chat-head-title, .chat-head-meta, .chat-head-actions */
  /* .model-chip, .thread-scroll, .mem-banner, .link-btn */
  /* .msg, .msg-head, .avatar-sm, .avatar-asst, .who-name, .ts, .msg-body, .msg-body.md
     (and all child selectors), .msg-user, .msg-asst, .attach-list, .attach-chip, .msg-actions */
}
```

- [ ] **Step 2.3: Update `useIsMobile` to write `data-density` alongside `compact` class**

Modify `frontend/src/hooks/useIsMobile.ts` line 36:

```ts
document.documentElement.classList.toggle('compact', isMobileDevice);
document.documentElement.setAttribute('data-density', isMobileDevice ? 'compact' : 'comfortable');
```

- [ ] **Step 2.4: Boot smoke test**

```bash
cd frontend && pnpm dev --host
```

Open the network URL. Expected: app boots, fonts swap to IBM Plex Sans, base background switches to `--l-bg` (warm off-white) in light mode. Existing screens render with old structure but new colors and font.

- [ ] **Step 2.5: Commit**

```bash
git add frontend/src/styles/app.css frontend/src/hooks/useIsMobile.ts frontend/src/router.tsx
# (or whatever file received the head links)
git commit -m "feat(design-v2): tokens, fonts, theme + density attributes"
```

---

## Task 3: Migrate App Shell (topbar, sidebar, mobile shell)

**Files:**
- Create: `frontend/src/components/layout/AppTopbar.tsx`
- Modify: `frontend/src/components/layout/AppShell.tsx`
- Modify: `frontend/src/components/layout/AppSidebar.tsx`
- Modify: `frontend/src/components/layout/MobileAppShell.tsx`, `MobileHeader.tsx`, `BottomTabBar.tsx`, `ConversationDrawer.tsx`
- Test: `frontend/e2e/shell/*.spec.ts` (selector updates)

- [ ] **Step 3.1: Read the Vortex chrome reference**

Open `.design-bundle-vortex/project/src/chrome.jsx` and `.design-bundle-vortex/project/Vortex.html` (style block lines ~95–276 cover `.app`, `.topbar`, `.brand`, `.sidebar`). Note the brand mark, search field, status chip, sidebar layout (top nav + inline conv list + footer org card).

- [ ] **Step 3.2: Read the failing E2E test**

```bash
cd frontend && pnpm test:e2e:filter shell
```

Expected: existing shell tests pass against current chrome. Note which selectors they use (likely `data-testid` or text matchers) — those become the contract you must preserve while restructuring DOM.

- [ ] **Step 3.3: Implement `AppTopbar.tsx`**

Create `frontend/src/components/layout/AppTopbar.tsx`. The component renders the 44px-tall top row: brand block (matches sidebar's 220px width), search field, right cluster.

```tsx
import { Link } from '@tanstack/react-router';
import { useThemeMode } from '@/hooks/useThemeMode'; // create later if absent — for now read document.documentElement attribute
// Replace lucide icons with what's already in the project (lucide-react is in deps).
import { Search, Sun, Moon, ChevronDown } from 'lucide-react';

export function AppTopbar() {
  return (
    <header className="topbar" data-testid="app-topbar">
      <Link to="/" className="brand" aria-label="Home">
        <span className="brand-mark" aria-hidden>VX</span>
        <span className="brand-name">Vortex</span>
        <span className="brand-env mono">DEV</span>
      </Link>

      <div className="topbar-search" role="search">
        <Search size={14} aria-hidden />
        <input type="text" placeholder="Search…" aria-label="Search" />
        <kbd>⌘K</kbd>
      </div>

      <div className="topbar-right">
        <span className="topbar-chip" data-testid="topbar-health">
          <span className="dot" aria-hidden /> Healthy
        </span>
        <span className="divider" aria-hidden />
        <ThemeToggle />
        <button className="avatar" aria-label="Account">DN</button>
      </div>
    </header>
  );
}

function ThemeToggle() {
  const toggle = () => {
    const cur = document.documentElement.getAttribute('data-theme') ?? 'light';
    document.documentElement.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
  };
  return (
    <button onClick={toggle} aria-label="Toggle theme" className="topbar-chip">
      <Sun size={12} className="dark:hidden" />
      <Moon size={12} className="hidden dark:inline" />
    </button>
  );
}
```

(Avatar initials and brand text are placeholder for this task; Task 3.5 hooks them to `useCurrentUserQuery`.)

- [ ] **Step 3.4: Restructure `AppShell.tsx`**

Replace the existing shell layout with the Vortex grid:

```tsx
import { AppTopbar } from './AppTopbar';
import { AppSidebar } from './AppSidebar';

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="app">
      <AppTopbar />
      <AppSidebar />
      <main className="main">{children}</main>
    </div>
  );
}
```

Where `.app` grid is defined in the design-system layer (Task 2): `display: grid; grid-template-columns: 220px 1fr; grid-template-rows: 44px 1fr; height: 100dvh; min-height: 100dvh;`.

(Existing logic in `AppShell` for outlets, error boundaries, sidebar collapse — preserve, just move into the new grid.)

- [ ] **Step 3.5: Restructure `AppSidebar.tsx`**

```tsx
import { Link, useRouterState } from '@tanstack/react-router';
import { useConversationsListQuery } from '@/hooks/useConversationsListQuery'; // adjust to actual path
import { useCurrentUserQuery } from '@/hooks/useCurrentUserQuery';

const NAV = [
  { to: '/chat', n: '01', label: 'Chat' },
  { to: '/knowledge-bases', n: '02', label: 'Knowledge' },
  { to: '/memories', n: '03', label: 'Memories' },
  { to: '/org/settings', n: '04', label: 'Org Settings' },
] as const;

export function AppSidebar() {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const conversations = useConversationsListQuery();
  const user = useCurrentUserQuery();

  return (
    <aside className="sidebar" data-testid="app-sidebar">
      <nav className="side-section" aria-label="Primary">
        <div className="side-label">Workspace</div>
        {NAV.map(({ to, n, label }) => (
          <Link
            key={to}
            to={to}
            className={`side-item ${path.startsWith(to) ? 'active' : ''}`}
            data-testid={`nav-${label.toLowerCase().replace(/\s+/g, '-')}`}
          >
            <span className="side-icon mono">{n}</span>
            <span>{label}</span>
          </Link>
        ))}
      </nav>

      <div className="side-section-convs">
        <div className="side-label-row">
          <span className="side-label">Recent</span>
          <Link to="/chat" className="btn btn-xs">New</Link>
        </div>
        {conversations.data?.slice(0, 12).map((c) => (
          <Link
            key={c.id}
            to="/chat/conversations/$conversationId"
            params={{ conversationId: c.id }}
            className={`conv-mini ${path.endsWith(c.id) ? 'active' : ''}`}
          >
            <span className="title">{c.title ?? 'Untitled'}</span>
            <span className="meta mono">{relativeTime(c.updatedAt)}</span>
          </Link>
        ))}
      </div>

      <div className="sidebar-foot">
        <div className="org-card">
          <div className="avatar">{(user.data?.name ?? '?').slice(0, 2).toUpperCase()}</div>
          <div>
            <div className="name">{user.data?.name ?? 'Loading…'}</div>
            <div className="meta mono">{user.data?.role ?? ''}</div>
          </div>
        </div>
      </div>
    </aside>
  );
}

function relativeTime(iso?: string) {
  if (!iso) return '';
  const d = (Date.now() - new Date(iso).getTime()) / 60000;
  if (d < 60) return `${Math.max(1, Math.round(d))}m`;
  if (d < 60 * 24) return `${Math.round(d / 60)}h`;
  return `${Math.round(d / (60 * 24))}d`;
}
```

(If the actual hooks have different names, adjust. Use `pnpm tsc --noEmit` to verify.)

- [ ] **Step 3.6: Restyle mobile shell with tokens**

`MobileAppShell.tsx`, `MobileHeader.tsx`, `BottomTabBar.tsx`, `ConversationDrawer.tsx`: keep behavior, swap inline styles / Tailwind classes referencing old palette to the new token utilities (`bg-panel`, `text-ink`, `border-line`, etc.). Mobile header copies the `.brand` cluster from `AppTopbar`.

- [ ] **Step 3.7: Update shell E2E selectors**

In `frontend/e2e/shell/*.spec.ts`, replace any selector targeting old shell classes (`.app-header`, `[data-testid="sidebar-old"]`, etc.) with new ones (`[data-testid="app-topbar"]`, `[data-testid="app-sidebar"]`, `[data-testid="nav-chat"]`).

- [ ] **Step 3.8: Run shell E2E**

```bash
cd frontend && pnpm test:e2e:filter shell
```

Expected: all shell specs pass. If failing on missing data attributes, add them in the components and re-run.

- [ ] **Step 3.9: Visual smoke**

```bash
pnpm dev --host
```

Open the network URL. Expected: 44px topbar with brand, search, status chip; 220px sidebar with nav + recent conversations + org card; main column scrolls inside grid.

- [ ] **Step 3.10: Commit**

```bash
git add frontend/src/components/layout frontend/e2e/shell
git commit -m "feat(design-v2): vortex app shell — topbar, sidebar, mobile chrome"
```

---

## Task 4: Migrate Auth pages (split-screen)

**Files:**
- Create: `frontend/src/components/auth/AuthShell.tsx`, `AuthFormCard.tsx`
- Modify: `frontend/src/routes/login.tsx`, `register.tsx`, `setup.tsx`
- Test: `frontend/e2e/auth/*.spec.ts` + new `frontend/e2e/auth/auth-split-layout.spec.ts`

- [ ] **Step 4.1: Read the Auth reference**

Open `.design-bundle-landing/project/Auth.html`. Note the structure: `<aside class="hero">` (left, branding + decorative rays + footer line) and `<section class="form-side">` (right, centered form card with header + fields + divider + SSO + footer link). Copy the relevant CSS into `app.css` `@layer components` (a small new cluster: `.auth-grid`, `.auth-hero`, `.hero-top`, `.hero-center`, `.hero-bottom`, `.auth-form-side`, `.auth-form-card`, `.auth-divider`, `.auth-sso-row`).

- [ ] **Step 4.2: Implement `AuthShell.tsx`**

```tsx
import type { ReactNode } from 'react';
import { Link } from '@tanstack/react-router';

export function AuthShell({ children, heroTagline }: { children: ReactNode; heroTagline: string }) {
  return (
    <div className="auth-grid" data-testid="auth-shell">
      <aside className="auth-hero">
        <div className="hero-top">
          <Link to="/" className="brand" aria-label="Home">
            <span className="brand-mark" aria-hidden>VX</span>
            <span className="brand-name">Vortex</span>
          </Link>
        </div>
        <div className="hero-center">
          <div className="auth-rays" aria-hidden />
          <p className="serif text-2xl text-ink leading-tight max-w-[28ch]">{heroTagline}</p>
        </div>
        <div className="hero-bottom mono text-ink-3 text-xs">
          Trusted by enterprise teams · Build {import.meta.env.VITE_BUILD_ID ?? 'dev'}
        </div>
      </aside>
      <section className="auth-form-side">
        <div className="auth-form-card">{children}</div>
      </section>
    </div>
  );
}
```

- [ ] **Step 4.3: Implement `AuthFormCard.tsx`**

```tsx
import type { ReactNode } from 'react';

export function AuthFormCard({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div data-testid="auth-form-card">
      <header className="mb-6">
        <h1 className="text-xl font-semibold text-ink leading-tight">{title}</h1>
        {subtitle && <p className="text-ink-3 text-sm mt-1">{subtitle}</p>}
      </header>
      <div className="flex flex-col gap-4">{children}</div>
      {footer && <footer className="mt-6 text-sm text-ink-3">{footer}</footer>}
    </div>
  );
}
```

- [ ] **Step 4.4: Wrap `login.tsx`**

Restructure the existing route component so the entire return is wrapped in `<AuthShell>` + `<AuthFormCard>`:

```tsx
import { AuthShell } from '@/components/auth/AuthShell';
import { AuthFormCard } from '@/components/auth/AuthFormCard';
import { Link } from '@tanstack/react-router';

// ...existing imports/hooks/state preserved...

return (
  <AuthShell heroTagline="Ask anything. Know everything.">
    <AuthFormCard
      title="Sign in"
      subtitle="Use your work email."
      footer={<>New here? <Link to="/register" className="text-accent">Create an account</Link></>}
    >
      {/* existing form JSX, but inputs use design-system classes:
          <input className="textarea" /> or Tailwind utilities (text-ink, border-line, bg-panel) */}
    </AuthFormCard>
  </AuthShell>
);
```

Preserve all existing state, mutations, validation, redirects.

- [ ] **Step 4.5: Wrap `register.tsx` and `setup.tsx` the same way**

`register.tsx` heroTagline: `"Set up your workspace in minutes."` Footer: `<>Already have an account? <Link to="/login" className="text-accent">Sign in</Link></>`

`setup.tsx` heroTagline: `"First run — bootstrap your org."` No footer link (or admin-only docs link).

- [ ] **Step 4.6: Update `frontend/e2e/auth/*.spec.ts` selectors**

Replace any reference to old auth wrappers with `[data-testid="auth-shell"]`, `[data-testid="auth-form-card"]`. Keep all behavioral assertions (submit, error display, redirect) intact.

- [ ] **Step 4.7: Add `auth-split-layout.spec.ts`**

```ts
import { test, expect } from '@playwright/test';

test.describe('Auth split layout', () => {
  test('login shows hero + form side by side on desktop', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/login');
    await expect(page.getByTestId('auth-shell')).toBeVisible();
    await expect(page.getByTestId('auth-form-card')).toBeVisible();
    const hero = page.locator('.auth-hero');
    const form = page.locator('.auth-form-side');
    const heroBox = await hero.boundingBox();
    const formBox = await form.boundingBox();
    expect(heroBox).not.toBeNull();
    expect(formBox).not.toBeNull();
    expect(formBox!.x).toBeGreaterThan(heroBox!.x + heroBox!.width - 4);
  });

  test('login collapses hero on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/login');
    await expect(page.getByTestId('auth-form-card')).toBeVisible();
    const hero = page.locator('.auth-hero');
    const heroBox = await hero.boundingBox();
    // Hero should collapse to a header strip <= 200px tall on mobile.
    expect(heroBox!.height).toBeLessThanOrEqual(200);
  });

  test('register and setup also use the split shell', async ({ page }) => {
    await page.goto('/register');
    await expect(page.getByTestId('auth-shell')).toBeVisible();
    await page.goto('/setup');
    await expect(page.getByTestId('auth-shell')).toBeVisible();
  });
});
```

- [ ] **Step 4.8: Run auth E2E**

```bash
cd frontend && pnpm test:e2e:filter auth
```

Expected: green. Iterate until all assertions pass.

- [ ] **Step 4.9: Visual check**

```bash
pnpm dev --host
```

Visit `/login`, `/register`, `/setup` desktop + mobile widths. Compare side-by-side with `.design-bundle-landing/project/Auth.html` opened in a separate tab.

- [ ] **Step 4.10: Commit**

```bash
git add frontend/src/components/auth frontend/src/routes/login.tsx frontend/src/routes/register.tsx frontend/src/routes/setup.tsx frontend/e2e/auth frontend/src/styles/app.css
git commit -m "feat(design-v2): auth pages — split-screen shell + form card"
```

---

## Task 5: Migrate Chat screen (3-col grid + inspector)

**Files:**
- Create: `frontend/src/components/chat/ConversationInspectorPanel.tsx`
- Modify: `frontend/src/components/chat/ConversationsRouteLayout.tsx`, `ConversationThreadPage.tsx`, `ConversationsSidebarPanel.tsx`, `ChatComposerDock.tsx`, `ChatComposerDockMobile.tsx`, `ThreadItemChip.tsx`, `MarkdownMessage.tsx`
- Test: `frontend/e2e/chat/*.spec.ts` + new `frontend/e2e/chat/chat-three-col-layout.spec.ts`

- [ ] **Step 5.1: Read the Vortex chat reference**

Open `.design-bundle-vortex/project/src/screen_chat.jsx` (full read) and the chat CSS in `Vortex.html` lines ~1052–1701. Note the 3-col grid (`280px 1fr 320px`), `.conv-list`, `.chat-main`, `.thread-scroll`, `.compose-box`, `.mem-banner`, message styling for `.msg-user` vs `.msg-asst`, capability tag chips (`.cap-tag`).

- [ ] **Step 5.2: Restructure `ConversationsRouteLayout.tsx`**

Replace the layout's outer div with:

```tsx
const [inspectorOpen, setInspectorOpen] = useState(false);

return (
  <div className={`chat-grid ${inspectorOpen ? '' : 'chat-grid-2col'}`} data-testid="chat-layout">
    <ConversationsSidebarPanel />
    <Outlet />
    {inspectorOpen && <ConversationInspectorPanel />}
  </div>
);
```

Pass `inspectorOpen` and `setInspectorOpen` down via context (`ConversationsOutletContext.tsx`) so the thread page can toggle it.

- [ ] **Step 5.3: Restyle `ConversationsSidebarPanel.tsx`**

Convert to the `.conv-list` shape: header with `.conv-list-search` (search input), `.conv-list-scroll` body grouped by `.conv-grp-label` (Today / Yesterday / Earlier), each row `.conv-row` with `.top` (title + `.when`), `.preview` (2-line clamp), `.meta` (mono caps, capability tag chips). Active row gets `active` class.

```tsx
function groupByRecency(convs: Conversation[]) {
  const today: Conversation[] = [];
  const yesterday: Conversation[] = [];
  const earlier: Conversation[] = [];
  const now = Date.now();
  for (const c of convs) {
    const days = (now - new Date(c.updatedAt).getTime()) / (1000 * 60 * 60 * 24);
    if (days < 1) today.push(c);
    else if (days < 2) yesterday.push(c);
    else earlier.push(c);
  }
  return { today, yesterday, earlier };
}
```

Render groups via `<div className="conv-grp-label">Today</div>` etc.

- [ ] **Step 5.4: Restyle `ConversationThreadPage.tsx`**

Outer wrap: `.chat-main` containing `.chat-head` and `.thread-scroll` and the composer.

```tsx
<div className="chat-main">
  <div className="chat-head">
    <div className="chat-head-title">
      <h2>{conversation.title}</h2>
      <div className="chat-head-meta mono">
        <span className="model-chip"><span className="name">{model.name}</span> <span className="effort">{model.effort}</span></span>
        <span className="sep">·</span>
        <span>{messages.length} msgs</span>
      </div>
    </div>
    <div className="chat-head-actions">
      <button className={`btn btn-sm ${memoryOn ? 'active' : ''}`} onClick={...}>Memory</button>
      <button className={`btn btn-sm ${inspectorOpen ? 'active' : ''}`} onClick={() => setInspectorOpen((v) => !v)} data-testid="toggle-inspector">Inspect</button>
      <button className="btn btn-sm">Share</button>
    </div>
  </div>

  <div className="thread-scroll">
    {memoryHits.length > 0 && (
      <div className="mem-banner">
        <b>Memory</b> <span className="muted">retrieved {memoryHits.length} entries</span>
        <button className="link-btn">View →</button>
      </div>
    )}
    {messages.map((m) => <Message key={m.id} m={m} />)}
  </div>

  <div className="run-compose">
    <ChatComposerDock />
  </div>
</div>
```

- [ ] **Step 5.5: Restyle messages**

Replace the existing message component with:

```tsx
function Message({ m }: { m: ThreadMessage }) {
  const isUser = m.role === 'user';
  return (
    <article className={`msg ${isUser ? 'msg-user' : 'msg-asst'}`} data-testid={`msg-${m.role}`} data-msg-id={m.id}>
      <header className="msg-head">
        <span className={`avatar-sm ${isUser ? '' : 'avatar-asst'} mono`}>{isUser ? 'YO' : 'VX'}</span>
        <span className="who-name">{isUser ? 'You' : m.modelName ?? 'Assistant'}</span>
        <span className="ts mono">{formatTs(m.createdAt)}</span>
      </header>
      <div className="msg-body md">
        <MarkdownMessage content={m.content} />
      </div>
      {m.attachments?.length ? (
        <div className="attach-list">
          {m.attachments.map((a) => <span key={a.id} className="attach-chip">{a.name}</span>)}
        </div>
      ) : null}
      {!isUser && (
        <div className="msg-actions">
          <button className="btn btn-sm">Copy</button>
          <button className="btn btn-sm">Regenerate</button>
        </div>
      )}
    </article>
  );
}
```

`MarkdownMessage` already exists — keep its rendering, but ensure the parent `.msg-body.md` styles cascade correctly (blockquote, code, list, etc., handled by the design-system block in app.css).

- [ ] **Step 5.6: Restyle `ChatComposerDock.tsx`**

Outer: `.compose-box`. Textarea uses `.textarea`. Compose row: model picker + capability toggles + send.

```tsx
<div className="compose-box">
  <textarea className="textarea" placeholder="Ask Vortex…" />
  <div className="compose-row">
    <ModelCatalogPicker />
    <button className="btn btn-sm">Reflection</button>
    <button className="btn btn-sm">Research</button>
    <button className="btn btn-accent btn-sm" style={{ marginLeft: 'auto' }}>Send</button>
  </div>
</div>
```

`ChatComposerDockMobile.tsx` mirrors but compresses to a single row.

- [ ] **Step 5.7: Restyle `ThreadItemChip.tsx` to `.cap-tag`**

```tsx
export function ThreadItemChip({ icon, label, tone }: { icon?: ReactNode; label: string; tone?: 'ok' | 'warn' | 'err' }) {
  return (
    <span className={`cap-tag ${tone ? `pill-${tone}` : ''}`}>
      {icon}
      <span>{label}</span>
    </span>
  );
}
```

- [ ] **Step 5.8: Implement `ConversationInspectorPanel.tsx`**

```tsx
import { useConversationsOutletContext } from '@/contexts/ConversationsOutletContext';

export function ConversationInspectorPanel() {
  const { activeMessage } = useConversationsOutletContext();
  return (
    <aside className="run-inspect" data-testid="conversation-inspector">
      <div className="inspect-sec">
        <div className="section-head">Message</div>
        <div className="kv">
          <div>ID</div><div className="mono">{activeMessage?.id ?? '—'}</div>
          <div>Model</div><div className="mono">{activeMessage?.modelName ?? '—'}</div>
          <div>Tokens</div><div className="mono">{activeMessage?.usage?.totalTokens ?? '—'}</div>
        </div>
      </div>
      <div className="inspect-sec">
        <div className="section-head">Tool calls</div>
        {/* TODO: backend currently does not surface per-message tool traces — render placeholder */}
        <p className="text-ink-3 text-xs">No trace data exposed yet.</p>
      </div>
      <div className="inspect-sec">
        <div className="section-head">Retrieval hits</div>
        {/* TODO: wire to KB hit data once API exposes it per message */}
        <p className="text-ink-3 text-xs">No retrieval data exposed yet.</p>
      </div>
    </aside>
  );
}
```

(If `useConversationsOutletContext` doesn't expose `activeMessage`, add it: track which message the user clicked via the existing message component's `onClick`.)

- [ ] **Step 5.9: Update chat E2E selectors**

In `frontend/e2e/chat/*.spec.ts`, swap any selectors keyed on old layout (`.thread`, `.composer`, etc.) for new ones (`[data-testid="chat-layout"]`, `[data-testid="msg-user"]`, `[data-testid="msg-assistant"]`, `[data-testid="toggle-inspector"]`, `.thread-scroll`).

- [ ] **Step 5.10: Add `chat-three-col-layout.spec.ts`**

```ts
import { test, expect } from '@playwright/test';
import { createOrFindConversation } from '../support/ui-helpers';

test('chat shows 3-col with inspector toggle', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/chat');
  await createOrFindConversation(page, 'E2E Shared Conversation');

  await expect(page.getByTestId('chat-layout')).toBeVisible();
  await expect(page.locator('.conv-list')).toBeVisible();
  await expect(page.locator('.chat-main')).toBeVisible();

  // Inspector closed by default.
  await expect(page.getByTestId('conversation-inspector')).toBeHidden();

  await page.getByTestId('toggle-inspector').click();
  await expect(page.getByTestId('conversation-inspector')).toBeVisible();

  await page.getByTestId('toggle-inspector').click();
  await expect(page.getByTestId('conversation-inspector')).toBeHidden();
});

test('chat collapses to single column on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/chat');
  // Mobile shows the conversation list as a drawer; main thread visible by default.
  await expect(page.locator('.chat-main')).toBeVisible();
});
```

- [ ] **Step 5.11: Run chat E2E**

```bash
cd frontend && pnpm test:e2e:filter chat
```

Iterate until green. Streaming tests are the fragile ones — verify `.thread-scroll` selector still finds the scrollable region.

- [ ] **Step 5.12: Visual check**

```bash
pnpm dev --host
```

Open `/chat`. Compare against `.design-bundle-vortex/project/Vortex.html` (chat is the default screen). Verify message bubbles, capability chips, composer dock, mem-banner appearance.

- [ ] **Step 5.13: Commit**

```bash
git add frontend/src/components/chat frontend/src/contexts frontend/e2e/chat frontend/src/styles/app.css
git commit -m "feat(design-v2): chat 3-col layout — sidebar, thread, inspector, composer"
```

---

## Task 6: Migrate Knowledge Bases (master/detail)

**Files:**
- Modify: `frontend/src/routes/knowledge-bases/index.tsx`, `$id.tsx`
- Modify: `frontend/src/components/knowledge-bases/*`
- Test: `frontend/e2e/kb/*.spec.ts`

- [ ] **Step 6.1: Read the Vortex KB reference**

`.design-bundle-vortex/project/src/screen_kb.jsx` — note the master/detail structure: index = `.kpi-row` strip + `.tbl` listing; detail = 2-col `.run-grid` (left list, right preview).

- [ ] **Step 6.2: Restyle KB index (`index.tsx`)**

```tsx
return (
  <div className="main-inner">
    <header className="screen-head">
      <h1>Knowledge bases</h1>
      <div className="kpi-row">
        <div className="kpi"><div className="kpi-label">KBs</div><div className="kpi-value">{stats.total}</div></div>
        <div className="kpi"><div className="kpi-label">Documents</div><div className="kpi-value">{stats.docs}</div></div>
        <div className="kpi"><div className="kpi-label">Retrievals · 7d</div><div className="kpi-value">{stats.retrievals7d}</div></div>
      </div>
      <div style={{ marginLeft: 'auto' }}>
        <button className="btn btn-primary">New KB</button>
      </div>
    </header>

    <table className="tbl" data-testid="kb-list">
      <thead><tr><th>Name</th><th>Docs</th><th>Updated</th><th>Status</th><th>Provider</th></tr></thead>
      <tbody>
        {kbs.map((kb) => (
          <tr key={kb.id} onClick={() => navigate({ to: '/knowledge-bases/$id', params: { id: kb.id } })}>
            <td>{kb.name}</td>
            <td className="mono">{kb.docCount}</td>
            <td className="mono">{relativeTime(kb.updatedAt)}</td>
            <td><span className={`pill pill-${statusTone(kb.status)}`}>{kb.status}</span></td>
            <td><span className="prov"><span className={`prov-mark ${kb.providerKey}`} />{kb.providerLabel}</span></td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);
```

If `stats` aren't currently fetched, derive locally from `kbs` (skip retrievals7d — placeholder `—`).

- [ ] **Step 6.3: Restyle KB detail (`$id.tsx`)**

```tsx
return (
  <div className="run-grid" data-testid="kb-detail">
    <div className="run-list">
      {/* doc list / connectors / ingestion runs */}
      {docs.map((d) => (
        <div className="run-list-item" key={d.id}>
          <div className="title">{d.title}</div>
          <div className="meta mono">{relativeTime(d.ingestedAt)} · {d.chunks} chunks</div>
        </div>
      ))}
    </div>
    <div className="run-main">
      <div className="run-scroll">
        {/* doc preview / chunk inspector */}
      </div>
      <div className="run-inspect">
        {/* connector config, KB metadata */}
      </div>
    </div>
  </div>
);
```

Wire upload + connector flows from existing components (`CreateKnowledgeBaseDialog`, `KnowledgeBaseConnectorsSection`) into the new structure.

- [ ] **Step 6.4: Update KB E2E selectors**

Update `frontend/e2e/kb/*.spec.ts` to use `[data-testid="kb-list"]`, `[data-testid="kb-detail"]` and the new row/column locators.

- [ ] **Step 6.5: Run KB E2E**

```bash
cd frontend && pnpm test:e2e:filter kb
```

Iterate until green.

- [ ] **Step 6.6: Visual check**

```bash
pnpm dev --host
```

Visit `/knowledge-bases` and a detail page. Verify KPI strip, table styling, master/detail split.

- [ ] **Step 6.7: Commit**

```bash
git add frontend/src/routes/knowledge-bases frontend/src/components/knowledge-bases frontend/e2e/kb
git commit -m "feat(design-v2): knowledge bases — kpi strip, master/detail"
```

---

## Task 7: Migrate Memories (list/detail)

**Files:**
- Modify: `frontend/src/components/memories/MemoriesPage.tsx`, `frontend/src/routes/memories.tsx`
- Test: `frontend/e2e/memories/*.spec.ts`

- [ ] **Step 7.1: Read the Vortex memories reference**

`.design-bundle-vortex/project/src/screen_memories.jsx` — list with filter chips, detail panel on the right.

- [ ] **Step 7.2: Restyle `MemoriesPage.tsx`**

```tsx
return (
  <div className="run-grid" data-testid="memories-page">
    <div className="run-list">
      <div className="filter-bar">
        {(['all', 'user', 'feedback', 'project', 'reference'] as const).map((t) => (
          <button
            key={t}
            className={`filter-chip ${filter === t ? 'active' : ''}`}
            onClick={() => setFilter(t)}
          >{t}</button>
        ))}
      </div>
      {filtered.map((m) => (
        <div
          key={m.id}
          className={`run-list-item ${active?.id === m.id ? 'active' : ''}`}
          onClick={() => setActive(m)}
        >
          <div className="title">{m.name ?? m.contentPreview}</div>
          <div className="meta mono">
            <span className={`pill pill-${typeTone(m.type)}`}>{m.type}</span>
            <span>{relativeTime(m.updatedAt)}</span>
          </div>
        </div>
      ))}
    </div>
    <div className="run-main">
      {active ? <MemoryDetail m={active} /> : <EmptyState label="Pick a memory to inspect." />}
    </div>
  </div>
);
```

CRUD endpoints unchanged — wire existing handlers into `MemoryDetail`.

- [ ] **Step 7.3: Update memories E2E selectors**

Replace any old selectors in `frontend/e2e/memories/*.spec.ts` with `[data-testid="memories-page"]` and the new list/detail classes.

- [ ] **Step 7.4: Run memories E2E**

```bash
cd frontend && pnpm test:e2e:filter memories
```

Iterate until green.

- [ ] **Step 7.5: Visual check**

```bash
pnpm dev --host
```

Visit `/memories`. Verify filter chips, list rows, detail panel.

- [ ] **Step 7.6: Commit**

```bash
git add frontend/src/components/memories frontend/src/routes/memories.tsx frontend/e2e/memories
git commit -m "feat(design-v2): memories — list with filters + detail panel"
```

---

## Task 8: Migrate Org Settings (Governance)

**Files:**
- Modify: `frontend/src/routes/org/settings.tsx`
- Modify: `frontend/src/components/admin/{AuditLogPanel,RbacPolicyPanel,RetentionPanel,UsagePanel}.tsx`
- Test: `frontend/e2e/admin/*.spec.ts`

- [ ] **Step 8.1: Read the Vortex governance reference**

`.design-bundle-vortex/project/src/screen_gov.jsx` — tabbed `.gov-grid` with `.policy-row` rows, `.audit-row` table, KPI header.

- [ ] **Step 8.2: Restyle `org/settings.tsx`**

```tsx
const [tab, setTab] = useState<'rbac' | 'audit' | 'retention' | 'usage'>('rbac');

return (
  <div className="main-inner" data-testid="org-settings">
    <header className="screen-head">
      <h1>Organization</h1>
      <div className="tabs">
        {(['rbac', 'audit', 'retention', 'usage'] as const).map((t) => (
          <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
            {tabLabel(t)}
          </button>
        ))}
      </div>
    </header>
    <div className="gov-grid">
      {tab === 'rbac' && <RbacPolicyPanel />}
      {tab === 'audit' && <AuditLogPanel />}
      {tab === 'retention' && <RetentionPanel />}
      {tab === 'usage' && <UsagePanel />}
    </div>
  </div>
);
```

- [ ] **Step 8.3: Restyle each admin panel**

`RbacPolicyPanel.tsx`: each policy row uses `.policy-row` with a `.switch` toggle + scope chips. `AuditLogPanel.tsx`: `.audit-row` table with action / actor / target / timestamp / mono trace ID. `RetentionPanel.tsx`: form rows in `.panel`, KPI header at top. `UsagePanel.tsx`: `.kpi-row` + `.chart` placeholder (existing chart kept; recolor lines/bars to `var(--accent)`).

For each: preserve existing TanStack Query hooks, mutations, validation. Only swap the JSX wrappers + classes.

- [ ] **Step 8.4: Update admin E2E selectors**

Update `frontend/e2e/admin/*.spec.ts` — `[data-testid="org-settings"]` and the tab/row locators.

- [ ] **Step 8.5: Run admin E2E**

```bash
cd frontend && pnpm test:e2e:filter admin
```

Iterate until green.

- [ ] **Step 8.6: Visual check**

```bash
pnpm dev --host
```

Visit `/org/settings`. Cycle through tabs. Verify policy switches, audit table, retention form, usage chart all use new tokens.

- [ ] **Step 8.7: Commit**

```bash
git add frontend/src/routes/org frontend/src/components/admin frontend/e2e/admin
git commit -m "feat(design-v2): org settings — gov-style tabs + policy/audit/retention/usage panels"
```

---

## Task 9: Token sweep — home, 404, error boundary

**Files:**
- Modify: `frontend/src/routes/index.tsx`, `frontend/src/components/home/*`
- Modify: `frontend/src/components/{DefaultCatchBoundary,NotFound}.tsx`

Note: structural Landing.html migration is tracked by `2026-04-15-vortex-landing-page-design.md`. This task is tokens only.

- [ ] **Step 9.1: Sweep home components**

In each file under `frontend/src/components/home/` and in `frontend/src/routes/index.tsx`, replace hardcoded color/text classes with token utilities (`bg-bg`, `text-ink`, `border-line`, `text-ink-3`, `bg-panel`). Replace any custom `dark:` prefixed colors with single token classes (the token already adapts to `data-theme`).

- [ ] **Step 9.2: Sweep error / 404**

`DefaultCatchBoundary.tsx` and `NotFound.tsx` — same token sweep. Use `.panel` for surface, `.btn` / `.btn-primary` for actions.

- [ ] **Step 9.3: Visual check**

Visit `/`, force a 404 by navigating to `/__nope__`, force a render error if possible. Verify everything reads tokens correctly under both `data-theme="light"` and `data-theme="dark"`.

- [ ] **Step 9.4: Run full E2E**

```bash
cd frontend && pnpm test:e2e
```

Expected: all green. This is the final integration check before merge.

- [ ] **Step 9.5: Commit**

```bash
git add frontend/src/routes/index.tsx frontend/src/components/home frontend/src/components/DefaultCatchBoundary.tsx frontend/src/components/NotFound.tsx
git commit -m "feat(design-v2): token sweep — home, 404, error boundary"
```

---

## Task 10: Final verification

- [ ] **Step 10.1: Full E2E pass on isolated worktree backend**

Verify worktree env loaded:

```bash
cat .worktree.env
```

Bring up E2E backend:

```bash
./scripts/e2e-up.sh
```

Confirm:

```bash
curl http://localhost:$E2E_API_PORT/health
```

Run full suite:

```bash
cd frontend && pnpm test:e2e
```

Expected: all specs green, 8 workers, 0 retries.

- [ ] **Step 10.2: TypeScript build**

```bash
cd frontend && pnpm build
```

Expected: build succeeds, no `tsc --noEmit` errors.

- [ ] **Step 10.3: Visual review checklist**

For each screen, open the corresponding bundle file in one browser tab and the live app in another. Verify side by side.

- `/login`, `/register`, `/setup` → `.design-bundle-landing/project/Auth.html`
- `/chat` → `.design-bundle-vortex/project/Vortex.html` (default screen)
- `/knowledge-bases` and `/knowledge-bases/<id>` → screen_kb section of Vortex.html
- `/memories` → screen_memories section
- `/org/settings` → screen_gov section
- `/` → token-only check (compare against current with new colors)

- [ ] **Step 10.4: Final commit (if any cleanups)**

```bash
git status
# If any straggling changes, commit them.
```

- [ ] **Step 10.5: Open PR (optional — defer to user)**

User decides whether to open a PR or merge locally. Use `superpowers:finishing-a-development-branch` if needed.

---

## Self-Review Notes

- **Spec coverage:** Each spec section maps to a task — Step 1 (tokens) → Task 2; Step 2 (shell) → Task 3; Step 3 (auth) → Task 4; Step 4 (chat) → Task 5; Step 5 (KB) → Task 6; Step 6 (memories) → Task 7; Step 7 (org) → Task 8; Step 8 (home/404) → Task 9. Worktree + CLAUDE.md from Section 1 → Tasks 0 + 1.
- **Type consistency:** `useConversationsListQuery`, `useCurrentUserQuery`, `useConversationsOutletContext` are referenced by name in plan code — verify their actual names/signatures during execution and adjust before commit. If a name differs, update the surrounding code in the same task; do not hand-wave.
- **Inspector data:** intentionally placeholder per the spec — TODO comments mark exactly which sections are stubs.
- **Tailwind v4:** all token registration uses `@theme` block in `app.css` (not a JS config file). Utility classes like `bg-bg`, `text-ink-2`, `border-line` work because `--color-bg` etc. live in `@theme`.
