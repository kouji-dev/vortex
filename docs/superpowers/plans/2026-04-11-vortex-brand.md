# Vortex Brand Components Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Vortex prism logo as an animated React component with 7 states and wire it into the chat streaming surface, sidebar header, and mobile nav.

**Architecture:** Three new brand components (`PrismLogo`, `VortexWordmark`, barrel `index.ts`) in `frontend/src/components/brand/`. Animations are CSS keyframes injected via a `<style>` tag inside `PrismLogo` (no Tailwind extension needed — keeps animations co-located and avoids build config changes). `ConversationThreadPage` derives a `PrismState` from existing `streaming`, `sendError` state. Sidebar and mobile header swap "AI Portal" text for the new lockup components.

**Tech Stack:** React 18, TypeScript, SVG, CSS keyframe animations (inline style tag), TanStack Router, Tailwind CSS (for layout only — not animation)

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `frontend/src/components/brand/PrismLogo.tsx` | **CREATE** | Animated SVG prism mark, 7 states, size prop |
| `frontend/src/components/brand/VortexWordmark.tsx` | **CREATE** | "Vortex" text, gradient/white/dark variants |
| `frontend/src/components/brand/index.ts` | **CREATE** | Barrel export |
| `frontend/src/components/layout/AppSidebar.tsx` | **MODIFY** | Replace "AI Portal" Link with PrismLogo + VortexWordmark lockup |
| `frontend/src/components/layout/MobileHeader.tsx` | **MODIFY** | Replace "AI Portal" Link with lockup on non-chat routes |
| `frontend/src/components/chat/ConversationThreadPage.tsx` | **MODIFY** | Replace "streaming…" header with PrismLogo wired to state; update "Waiting for tokens…" pulse |

---

## Task 1 — Create `PrismLogo.tsx`

**Files:**
- Create: `frontend/src/components/brand/PrismLogo.tsx`

The SVG uses an 80×80 internal viewBox scaled to the `size` prop. All animations are defined in a single `<style>` block rendered once inside the SVG. State drives which CSS class is applied to each group.

- [ ] **Step 1: Create the file**

```tsx
// frontend/src/components/brand/PrismLogo.tsx
import * as React from 'react'

export type PrismState =
  | 'idle'
  | 'loading'
  | 'streaming'
  | 'thinking'
  | 'error'
  | 'mono-white'
  | 'mono-dark'

interface PrismLogoProps {
  state?: PrismState
  size?: number
  className?: string
}

// Per-state color config
const STATE_COLORS: Record<
  PrismState,
  { outline: string; ray1: string; ray2: string; ray3: string; core: string; gradId: string }
> = {
  idle:         { outline: 'url(#prism-grad-violet)', ray1: '#f472b6', ray2: '#a78bfa', ray3: '#60a5fa', core: '#e0d7ff', gradId: 'prism-grad-violet' },
  loading:      { outline: 'url(#prism-grad-violet)', ray1: '#f472b6', ray2: '#a78bfa', ray3: '#60a5fa', core: '#e0d7ff', gradId: 'prism-grad-violet' },
  streaming:    { outline: 'url(#prism-grad-violet)', ray1: '#f472b6', ray2: '#a78bfa', ray3: '#60a5fa', core: '#e0d7ff', gradId: 'prism-grad-violet' },
  thinking:     { outline: 'url(#prism-grad-amber)',  ray1: '#fbbf24', ray2: '#f59e0b', ray3: '#fde68a', core: '#fde68a', gradId: 'prism-grad-amber'  },
  error:        { outline: 'url(#prism-grad-red)',    ray1: '#f87171', ray2: '#ef4444', ray3: '#fca5a5', core: '#fca5a5', gradId: 'prism-grad-red'    },
  'mono-white': { outline: '#e0d7ff', ray1: '#ffffff', ray2: '#ffffff', ray3: '#ffffff', core: '#ffffff', gradId: '' },
  'mono-dark':  { outline: '#1a1a2e', ray1: '#1a1a2e', ray2: '#1a1a2e', ray3: '#1a1a2e', core: '#1a1a2e', gradId: '' },
}

// Per-state animation class for the main prism group
const STATE_ANIM: Record<PrismState, string> = {
  idle:         'prism-idle',
  loading:      'prism-load',
  streaming:    'prism-stream',
  thinking:     'prism-think',
  error:        'prism-error',
  'mono-white': 'prism-idle',
  'mono-dark':  'prism-idle',
}

// Per-state ray opacity
const RAY_OPACITY: Record<PrismState, number> = {
  idle: 0.35, loading: 0.7, streaming: 0, thinking: 0, error: 0.7,
  'mono-white': 0.4, 'mono-dark': 0.4,
}

// States that use animated rays (sweep in/out)
const ANIMATED_RAYS = new Set<PrismState>(['streaming', 'thinking'])

export function PrismLogo({ state = 'idle', size = 64, className }: PrismLogoProps) {
  const c = STATE_COLORS[state]
  const animClass = STATE_ANIM[state]
  const useAnimRays = ANIMATED_RAYS.has(state)
  const rayOpacity = RAY_OPACITY[state]
  // Core radius: bigger pulse for streaming/thinking
  const coreR = state === 'streaming' ? 5 : state === 'thinking' ? 5 : 4
  const strokeWidth = size <= 16 ? 3 : 2
  const coreRBase = size <= 16 ? 7 : coreR

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 80 80"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="prism-grad-violet" x1="12" y1="8" x2="68" y2="72" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#f472b6" />
          <stop offset="50%"  stopColor="#a78bfa" />
          <stop offset="100%" stopColor="#60a5fa" />
        </linearGradient>
        <linearGradient id="prism-grad-amber" x1="12" y1="8" x2="68" y2="72" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#fbbf24" />
          <stop offset="50%"  stopColor="#f59e0b" />
          <stop offset="100%" stopColor="#fde68a" />
        </linearGradient>
        <linearGradient id="prism-grad-red" x1="12" y1="8" x2="68" y2="72" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#f87171" />
          <stop offset="50%"  stopColor="#ef4444" />
          <stop offset="100%" stopColor="#fca5a5" />
        </linearGradient>
        <style>{`
          /* ── Idle: slow gentle sway ── */
          .prism-idle { animation: prismIdleSway 4s ease-in-out infinite; transform-origin: 40px 40px; }
          @keyframes prismIdleSway {
            0%,100% { transform: rotate(-5deg); }
            50%     { transform: rotate(5deg); }
          }

          /* ── Loading: fast spin ── */
          .prism-load         { animation: prismSpin 1.2s linear infinite; transform-origin: 40px 40px; }
          .prism-load-trail1  { animation: prismSpin 1.2s linear infinite; transform-origin: 40px 40px; animation-delay: -0.1s; opacity: 0.25; }
          .prism-load-trail2  { animation: prismSpin 1.2s linear infinite; transform-origin: 40px 40px; animation-delay: -0.2s; opacity: 0.10; }
          @keyframes prismSpin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

          /* ── Streaming: pendulum 1.8s ── */
          .prism-stream        { animation: prismPendulum 1.8s ease-in-out infinite; transform-origin: 40px 40px; }
          .prism-stream-trail1 { animation: prismPendulum 1.8s ease-in-out infinite; transform-origin: 40px 40px; animation-delay: -0.1s; opacity: 0.20; }
          .prism-stream-trail2 { animation: prismPendulum 1.8s ease-in-out infinite; transform-origin: 40px 40px; animation-delay: -0.2s; opacity: 0.08; }
          @keyframes prismPendulum {
            0%   { transform: rotate(-18deg); }
            50%  { transform: rotate(18deg); }
            100% { transform: rotate(-18deg); }
          }

          /* ── Thinking: slow pendulum 3.5s ── */
          .prism-think        { animation: prismPendulum 3.5s ease-in-out infinite; transform-origin: 40px 40px; }
          .prism-think-trail1 { animation: prismPendulum 3.5s ease-in-out infinite; transform-origin: 40px 40px; animation-delay: -0.2s; opacity: 0.20; }
          .prism-think-trail2 { animation: prismPendulum 3.5s ease-in-out infinite; transform-origin: 40px 40px; animation-delay: -0.4s; opacity: 0.08; }

          /* ── Error: shake ── */
          .prism-error { animation: prismShake 0.5s ease-in-out infinite; transform-origin: 40px 40px; }
          @keyframes prismShake {
            0%,100% { transform: translateX(0) rotate(0deg); }
            15%     { transform: translateX(-4px) rotate(-3deg); }
            35%     { transform: translateX(4px) rotate(3deg); }
            55%     { transform: translateX(-3px) rotate(-2deg); }
            75%     { transform: translateX(3px) rotate(2deg); }
            90%     { transform: translateX(-1px) rotate(-1deg); }
          }

          /* ── Animated rays (streaming + thinking) ── */
          .prism-ray-sweep { stroke-dasharray: 70; animation: prismRaySweep var(--ray-dur, 1.8s) ease-in-out infinite; }
          .prism-ray-sweep-2 { animation-delay: 0.3s; }
          .prism-ray-sweep-3 { animation-delay: 0.6s; }
          @keyframes prismRaySweep {
            0%,100% { stroke-dashoffset: 70; opacity: 0; }
            40%,60% { stroke-dashoffset: 0; opacity: 0.9; }
          }

          /* ── Core pulses ── */
          .prism-core-stream { animation: prismCoreStream 1.8s ease-in-out infinite; }
          @keyframes prismCoreStream { 0%,100%{r:5} 50%{r:7;filter:drop-shadow(0 0 6px #a78bfa)} }

          .prism-core-think { animation: prismCoreThink 3.5s ease-in-out infinite; }
          @keyframes prismCoreThink { 0%,100%{r:5} 50%{r:6;filter:drop-shadow(0 0 10px #fbbf24)} }

          .prism-core-idle { animation: prismCoreIdle 4s ease-in-out infinite; }
          @keyframes prismCoreIdle { 0%,100%{r:4} 50%{r:5.5} }
        `}</style>
      </defs>

      {/* Ghost trails for loading */}
      {state === 'loading' && <>
        <g className="prism-load-trail2">
          <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke={c.outline} strokeWidth={strokeWidth} />
        </g>
        <g className="prism-load-trail1">
          <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke={c.outline} strokeWidth={strokeWidth} />
        </g>
      </>}

      {/* Ghost trails for streaming */}
      {state === 'streaming' && <>
        <g className="prism-stream-trail2">
          <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke={c.outline} strokeWidth={strokeWidth} />
        </g>
        <g className="prism-stream-trail1">
          <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke={c.outline} strokeWidth={strokeWidth} />
        </g>
      </>}

      {/* Ghost trails for thinking */}
      {state === 'thinking' && <>
        <g className="prism-think-trail2">
          <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke={c.outline} strokeWidth={strokeWidth} />
        </g>
        <g className="prism-think-trail1">
          <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke={c.outline} strokeWidth={strokeWidth} />
        </g>
      </>}

      {/* Main prism outline */}
      <g className={animClass}>
        <polygon
          points="40,8 68,40 40,72 12,40"
          fill="none"
          stroke={c.outline}
          strokeWidth={strokeWidth}
        />
      </g>

      {/* Rays */}
      {useAnimRays ? (
        <>
          <line x1="40" y1="8" x2="68" y2="40" stroke={c.ray1} strokeWidth={strokeWidth}
            className="prism-ray-sweep"
            style={{ '--ray-dur': state === 'thinking' ? '3.5s' : '1.8s' } as React.CSSProperties} />
          <line x1="40" y1="8" x2="40" y2="72" stroke={c.ray2} strokeWidth={strokeWidth}
            className="prism-ray-sweep prism-ray-sweep-2"
            style={{ '--ray-dur': state === 'thinking' ? '3.5s' : '1.8s' } as React.CSSProperties} />
          <line x1="40" y1="8" x2="12" y2="40" stroke={c.ray3} strokeWidth={strokeWidth}
            className="prism-ray-sweep prism-ray-sweep-3"
            style={{ '--ray-dur': state === 'thinking' ? '3.5s' : '1.8s' } as React.CSSProperties} />
        </>
      ) : (
        <>
          <line x1="40" y1="8" x2="68" y2="40" stroke={c.ray1} strokeWidth={strokeWidth} opacity={rayOpacity} />
          <line x1="40" y1="8" x2="40" y2="72" stroke={c.ray2} strokeWidth={strokeWidth} opacity={rayOpacity} />
          <line x1="40" y1="8" x2="12" y2="40" stroke={c.ray3} strokeWidth={strokeWidth} opacity={rayOpacity} />
        </>
      )}

      {/* Core dot */}
      <circle
        cx="40" cy="40"
        r={coreRBase}
        fill={c.core}
        className={
          state === 'streaming' ? 'prism-core-stream' :
          state === 'thinking'  ? 'prism-core-think'  :
          state === 'idle'      ? 'prism-core-idle'   : undefined
        }
      />
    </svg>
  )
}
```

- [ ] **Step 2: Verify file compiles (no TS errors)**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep brand
```
Expected: no output (no errors in brand files).

- [ ] **Step 3: Commit**

```bash
cd frontend && git add src/components/brand/PrismLogo.tsx
git commit -m "feat(brand): PrismLogo SVG component — 7 animated states"
```

---

## Task 2 — Create `VortexWordmark.tsx` + barrel `index.ts`

**Files:**
- Create: `frontend/src/components/brand/VortexWordmark.tsx`
- Create: `frontend/src/components/brand/index.ts`

- [ ] **Step 1: Create `VortexWordmark.tsx`**

```tsx
// frontend/src/components/brand/VortexWordmark.tsx
import * as React from 'react'

export type WordmarkVariant = 'gradient' | 'white' | 'dark'

interface VortexWordmarkProps {
  variant?: WordmarkVariant
  /** Font size in px. Default 17. Use ≥28 for gradient variant to look sharp. */
  size?: number
  className?: string
}

const VARIANT_STYLE: Record<WordmarkVariant, React.CSSProperties> = {
  gradient: {
    background: 'linear-gradient(90deg, #f472b6, #a78bfa, #60a5fa)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    backgroundClip: 'text',
  },
  white: { color: '#e0d7ff' },
  dark:  { color: '#1a1a2e' },
}

export function VortexWordmark({ variant = 'white', size = 17, className }: VortexWordmarkProps) {
  return (
    <span
      className={className}
      style={{
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        fontWeight: 700,
        fontSize: size,
        letterSpacing: '-0.03em',
        lineHeight: 1,
        userSelect: 'none',
        ...VARIANT_STYLE[variant],
      }}
    >
      Vortex
    </span>
  )
}
```

- [ ] **Step 2: Create `index.ts`**

```ts
// frontend/src/components/brand/index.ts
export { PrismLogo } from './PrismLogo'
export type { PrismState } from './PrismLogo'
export { VortexWordmark } from './VortexWordmark'
export type { WordmarkVariant } from './VortexWordmark'
```

- [ ] **Step 3: Verify compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep brand
```
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/brand/VortexWordmark.tsx frontend/src/components/brand/index.ts
git commit -m "feat(brand): VortexWordmark + barrel export"
```

---

## Task 3 — Wire brand into `AppSidebar`

**Files:**
- Modify: `frontend/src/components/layout/AppSidebar.tsx`

Replace the current "AI Portal" `<Link>` block (lines 33–41) with a lockup of `PrismLogo` (22px, idle/mono-white) + `VortexWordmark`.

- [ ] **Step 1: Update `AppSidebar.tsx`**

Add import at top of file (after existing imports):
```tsx
import { PrismLogo, VortexWordmark } from '~/components/brand'
```

Replace the `{!compact && ( <div className="min-w-0 flex-1 pr-1"> ... </div> )}` block with:
```tsx
{!compact && (
  <Link to="/" className="flex min-w-0 flex-1 items-center gap-2 pr-1">
    <PrismLogo state="mono-white" size={22} />
    <VortexWordmark variant="white" size={17} />
  </Link>
)}
{compact && (
  <Link to="/" aria-label="Vortex home">
    <PrismLogo state="mono-white" size={22} />
  </Link>
)}
```

Also remove the `<p className="truncate text-xs text-neutral-500">Signed-in workspace</p>` subtitle line — it's no longer needed with the branded lockup.

- [ ] **Step 2: Verify no TS errors**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -i "sidebar\|brand"
```
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/layout/AppSidebar.tsx
git commit -m "feat(brand): replace 'AI Portal' with Vortex lockup in sidebar"
```

---

## Task 4 — Wire brand into `MobileHeader`

**Files:**
- Modify: `frontend/src/components/layout/MobileHeader.tsx`

Replace "AI Portal" text on the non-chat route header (line 53) with the lockup.

- [ ] **Step 1: Update `MobileHeader.tsx`**

Add import at top:
```tsx
import { PrismLogo, VortexWordmark } from '~/components/brand'
```

Replace the non-chat-route `<header>` return (the second return, around line 47–54):
```tsx
return (
  <header className="flex h-12 shrink-0 items-center border-b border-neutral-200 bg-white px-4 dark:border-neutral-800 dark:bg-neutral-950">
    <Link to="/" className="flex items-center gap-2">
      <PrismLogo state="mono-white" size={20} />
      <VortexWordmark variant="white" size={18} />
    </Link>
  </header>
)
```

- [ ] **Step 2: Verify no TS errors**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -i "mobile\|brand"
```
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/layout/MobileHeader.tsx
git commit -m "feat(brand): replace 'AI Portal' with Vortex lockup in mobile header"
```

---

## Task 5 — Wire PrismLogo into chat streaming surface

**Files:**
- Modify: `frontend/src/components/chat/ConversationThreadPage.tsx`

Replace the current streaming header (the "assistant / streaming… / Stop" row at lines 1046–1062) and "Waiting for tokens…" pulse with `PrismLogo` wired to the correct state.

**State mapping:**
```
sendError !== null  → 'error'
streaming           → 'streaming'   (tokens flowing)
!streaming          → 'idle'        (post-stream chips still showing)
```
Note: `thinking` state will be added in a future task when `thinking_delta` SSE events are implemented. For now streaming covers both.

- [ ] **Step 1: Add import**

At the top of `ConversationThreadPage.tsx`, add after existing imports:
```tsx
import { PrismLogo } from '~/components/brand'
```

- [ ] **Step 2: Replace the streaming header block**

Find (lines 1046–1062):
```tsx
{streaming && (
<div className="mb-1.5 flex items-center justify-between gap-2">
  <span className="text-[10px] font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
    assistant
  </span>
  <div className="flex items-center gap-1">
    <span className="text-[10px] text-neutral-400">streaming…</span>
    <button
      type="button"
      className="rounded px-1.5 py-0.5 text-[10px] font-medium text-red-600 underline decoration-dotted dark:text-red-400"
      onClick={stopStream}
    >
      Stop
    </button>
  </div>
</div>
)}
```

Replace with:
```tsx
{streaming && (
  <div className="mb-2 flex items-center justify-between gap-2">
    <div className="flex items-center gap-2">
      <PrismLogo
        state={sendError ? 'error' : 'streaming'}
        size={20}
      />
      <span className="text-[11px] font-medium text-neutral-500 dark:text-neutral-400">
        {sendError ? 'Error' : 'Responding…'}
      </span>
    </div>
    <button
      type="button"
      className="rounded px-1.5 py-0.5 text-[10px] font-medium text-red-600 underline decoration-dotted dark:text-red-400"
      onClick={stopStream}
    >
      Stop
    </button>
  </div>
)}
```

- [ ] **Step 3: Replace "Waiting for tokens…" pulse**

Find (lines 1076–1080):
```tsx
) : streaming && streamThreadItems.length === 0 ? (
  <p className="flex items-center gap-2 text-sm text-neutral-400">
    <span className="inline-block h-3.5 w-0.5 animate-pulse rounded-full bg-neutral-400 dark:bg-neutral-500" />
    Waiting for tokens…
  </p>
```

Replace with:
```tsx
) : streaming && streamThreadItems.length === 0 ? (
  <div className="flex items-center gap-3">
    <PrismLogo state="loading" size={32} />
    <span className="text-sm text-neutral-400">Waiting for response…</span>
  </div>
```

- [ ] **Step 4: Verify no TS errors**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -i "conversation\|brand"
```
Expected: no output.

- [ ] **Step 5: Update input placeholder**

In `ConversationThreadPage.tsx`, find the chat input placeholder text. Search for `placeholder=` and update any "Message…" or similar placeholder to "Message Vortex…":

```bash
grep -n 'placeholder=' frontend/src/components/chat/ConversationThreadPage.tsx | head -5
```

If found, update the value to `"Message Vortex…"`.

If the placeholder lives in `ChatComposerDock.tsx` instead:
```bash
grep -rn 'placeholder=' frontend/src/components/chat/ChatComposerDock.tsx | head -5
```
Update the same way.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/chat/ConversationThreadPage.tsx
git commit -m "feat(brand): wire PrismLogo into chat streaming surface"
```

---

## Task 6 — Run E2E tests

The existing web-search and attachment E2E specs cover the chat surface. Run them to confirm the streaming surface changes didn't break anything.

- [ ] **Step 1: Ensure E2E backend is running**

```bash
curl -s http://localhost:8001/health
```
If not running:
```bash
./scripts/e2e-up.sh
```

- [ ] **Step 2: Run full E2E suite**

```bash
cd frontend && pnpm test:e2e
```
Expected: all tests pass.

- [ ] **Step 3: If any test fails**

Check if a selector targeted the old "streaming…" text or "assistant" label. Update the selector in the relevant spec to use `data-testid` or the new "Responding…" text.

- [ ] **Step 4: Commit test fixes if any**

```bash
git add frontend/e2e/
git commit -m "test(e2e): update selectors after streaming header rebrand"
```

---

## Future Tasks (not in this plan)

- **Thinking state wiring** — add `streamingThinking` state to `ConversationThreadPage` and switch logo to `'thinking'` when `thinking_delta` events arrive (part of the thinking streaming plan)
- **Favicon** — export 16px mono-white prism as `public/favicon.svg`
- **Splash / onboarding page** — use 56px mark + Style A gradient wordmark
