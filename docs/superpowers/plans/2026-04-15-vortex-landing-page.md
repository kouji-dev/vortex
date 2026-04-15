# Vortex Landing Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul `landing/` sub-project to match the approved Vortex dark marketing design with tabbed "How It Works", animated hero demo, and full brand identity.

**Architecture:** Replace the existing light-themed generic landing page inside `landing/` (TanStack Router + Start, React 19, Tailwind v4, Vite 8) with the Vortex design. Components live in `src/components/`, animation logic in `src/lib/`, scroll hooks in `src/hooks/`. The root layout (`__root.tsx`) owns the Nav + Footer shell; `routes/index.tsx` composes the page sections.

**Tech Stack:** React 19, TanStack Router (file-based), TanStack Start (SSR), Tailwind CSS v4, TypeScript, Playwright (E2E, to be added), `IntersectionObserver` + `requestAnimationFrame` for all animations — no canvas, no GSAP, no Three.js.

**Visual reference:** `docs/superpowers/vortex-landing-mockup.html` — open in browser, every pixel and timing is derived from this file.

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Modify | `src/styles/app.css` | Design tokens, animation keyframes, utility classes |
| Modify | `src/routes/__root.tsx` | AnnounceBanner + VortexNav + Footer shell |
| Modify | `src/routes/index.tsx` | Compose page sections |
| Create | `src/components/HeroSection.tsx` | Hero text + animated app demo frame |
| Create | `src/components/LogoBand.tsx` | CSS marquee logo strip |
| Create | `src/components/HowItWorks.tsx` | Tabbed section with all 4 panels |
| Create | `src/components/StatsSection.tsx` | 4-column count-up grid |
| Create | `src/components/MissionSection.tsx` | Centered quote block |
| Create | `src/components/CTASection.tsx` | Final CTA |
| Create | `src/lib/demo-hero.ts` | Hero looping chat animation sequence |
| Create | `src/lib/demo-chips.ts` | Process tab chip animation with AbortController |
| Create | `src/hooks/useScrollReveal.ts` | IntersectionObserver one-shot reveal |
| Create | `src/hooks/useCountUp.ts` | Count-up animation on scroll |
| Create | `playwright.config.ts` | Playwright config (port 5174, start dev server) |
| Create | `e2e/landing.spec.ts` | Full E2E coverage |

---

## Task 1: Design Tokens + Animation CSS

**Files:**
- Modify: `landing/src/styles/app.css`

- [ ] **Step 1: Replace app.css content**

```css
@import 'tailwindcss' source('../');

/* ── Design Tokens ── */
:root {
  --pink:   #f472b6;
  --violet: #a78bfa;
  --blue:   #60a5fa;
  --bg:     #040407;
  --bg2:    #07070e;
  --border: #161628;
  --b2:     #1e1e35;
  --text:   #e8e4ff;
  --muted:  #64748b;
  --dim:    #2a2a3e;
}

html { scroll-behavior: smooth; }

body {
  background: var(--bg);
  color: var(--text);
  -webkit-font-smoothing: antialiased;
}

/* ── Keyframes ── */
@keyframes prismSpin   { from{transform:rotate(0)}  to{transform:rotate(360deg)} }
@keyframes blink       { 0%,100%{opacity:1} 50%{opacity:0} }
@keyframes thinkBounce { 0%,60%,100%{transform:translateY(0);opacity:.3} 30%{transform:translateY(-5px);opacity:.9} }
@keyframes shineSweep  { 0%{background-position:100% 0} 100%{background-position:15% 0} }
@keyframes ticker      { from{transform:translateX(0)} to{transform:translateX(-50%)} }
@keyframes panelIn     { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }
@keyframes dotPulse    { 0%,100%{box-shadow:0 0 0 0 rgba(34,197,94,.5)} 50%{box-shadow:0 0 0 5px rgba(34,197,94,0)} }
@keyframes bgBreath    { 0%,100%{opacity:.7;transform:scale(1)} 50%{opacity:1;transform:scale(1.05)} }
@keyframes fadeDown    { from{opacity:0;transform:translateY(-18px)} to{opacity:1;transform:translateY(0)} }
@keyframes fadeUp      { from{opacity:0;transform:translateY(22px)}  to{opacity:1;transform:translateY(0)} }
@keyframes msway       { 0%,100%{transform:rotate(-6deg)} 50%{transform:rotate(6deg)} }

/* ── Scroll Reveal ── */
.reveal,.reveal-left,.reveal-right {
  opacity: 0;
  transition: opacity .75s ease, transform .75s ease;
}
.reveal       { transform: translateY(28px); }
.reveal-left  { transform: translateX(-32px); }
.reveal-right { transform: translateX(32px); }
.visible      { opacity: 1 !important; transform: none !important; }
.d1 { transition-delay: .1s }
.d2 { transition-delay: .2s }
.d3 { transition-delay: .3s }
.d4 { transition-delay: .4s }

/* ── Tool Chips ── */
.chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 10px; border-radius: 8px; font-size: 11px;
  border: 1px solid; font-family: inherit;
}
.chip-memory { border-color:rgba(59,130,246,.35); background:rgba(23,37,84,.4);  color:#93c5fd; }
.chip-kb     { border-color:rgba(126,34,206,.4);  background:rgba(59,7,100,.3);  color:#c4b5fd; }
.chip-web    { border-color:rgba(75,85,99,.5);    background:rgba(17,24,39,.5);  color:#9ca3af; }
.chip-check  { color: #22c55e; }

/* ── Cursor ── */
.cursor {
  display: inline-block; width: 2px; height: 13px;
  background: var(--violet); animation: blink .85s step-end infinite;
  vertical-align: middle; margin-left: 1px;
}

/* ── Thinking dots ── */
.thinking-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--violet); opacity: .3; display: inline-block;
  animation: thinkBounce 1.1s ease-in-out infinite;
}

/* ── Chat bubbles ── */
.msg-user { display: flex; justify-content: flex-end; }
.msg-user-bubble {
  max-width: 75%; padding: 9px 13px;
  background: #111122; border: 1px solid var(--b2);
  border-radius: 12px 12px 3px 12px;
  font-size: 13px; color: #c4b5fd; line-height: 1.55;
}
.msg-ai { display: flex; gap: 10px; align-items: flex-start; }
.msg-ai-avatar {
  width: 24px; height: 24px; border-radius: 7px;
  background: linear-gradient(135deg,var(--pink),var(--violet));
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; margin-top: 2px;
}
.msg-ai-name { font-size: 10px; font-weight: 600; color: #a78bfa; font-family: monospace; margin-bottom: 6px; }
.msg-ai-text { font-size: 13px; color: #9ca3af; line-height: 1.65; }

/* ── Composer ── */
.composer-textarea {
  flex: 1; min-height: 36px; max-height: 80px; resize: none;
  background: #0a0a18; border: 1px solid var(--border); border-radius: 9px;
  padding: 8px 12px; font-size: 13px; color: #c4b5fd; font-family: inherit;
  outline: none; line-height: 1.5; caret-color: var(--violet);
}
.composer-textarea::placeholder { color: #2a2a3e; }

/* ── Cap tags ── */
.cap-tag { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border: 1px solid; border-radius: 100px; font-size: 11px; font-weight: 500; }
.cap-reflection { border-color:rgba(59,130,246,.3);  background:rgba(23,37,84,.3);  color:#93c5fd; }
.cap-research   { border-color:rgba(126,34,206,.3);  background:rgba(59,7,100,.2);  color:#c4b5fd; }
.kb-tag { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border: 1px solid rgba(126,34,206,.3); background: rgba(59,7,100,.2); color: #c4b5fd; border-radius: 100px; font-size: 11px; font-weight: 500; }

/* ── Divider ── */
.section-divider { width: 100%; height: 1px; background: linear-gradient(90deg,transparent,rgba(167,139,250,.15),transparent); }

@layer base {
  *, ::after, ::before, ::backdrop, ::file-selector-button {
    border-color: var(--color-gray-200, currentcolor);
    box-sizing: border-box;
    margin: 0; padding: 0;
  }
}
```

- [ ] **Step 2: Verify build still works**

```bash
cd landing && pnpm build
```
Expected: no errors. The existing routes still compile; we just added CSS.

- [ ] **Step 3: Commit**

```bash
git add landing/src/styles/app.css
git commit -m "feat(landing): add Vortex design tokens and animation CSS"
```

---

## Task 2: Root Layout — Nav + Footer

**Files:**
- Modify: `landing/src/routes/__root.tsx`

- [ ] **Step 1: Write E2E smoke test (will fail — Playwright not set up yet, do this after Task 12)**

Skip for now; come back after Task 12 to write nav E2E tests.

- [ ] **Step 2: Replace `__root.tsx`**

```tsx
// landing/src/routes/__root.tsx
import { HeadContent, Link, Outlet, Scripts, createRootRoute } from '@tanstack/react-router'
import * as React from 'react'
import { getAppUrl } from '~/lib/app-url'
import appCss from '~/styles/app.css?url'

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: 'utf-8' },
      { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      { title: 'Vortex — AI Portal for Teams' },
      { name: 'description', content: 'Vortex connects the best AI models to your knowledge, memory, and team — in one place.' },
    ],
    links: [
      { rel: 'stylesheet', href: appCss },
      { rel: 'icon', href: '/favicon.ico' },
    ],
  }),
  component: RootComponent,
})

function RootComponent() {
  return (
    <html lang="en" style={{ background: 'var(--bg)' }}>
      <head><HeadContent /></head>
      <body style={{ background: 'var(--bg)', color: 'var(--text)', overflowX: 'hidden', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' }}>
        <AnnounceBanner />
        <VortexNav />
        <main><Outlet /></main>
        <VortexFooter />
        <Scripts />
      </body>
    </html>
  )
}

function AnnounceBanner() {
  return (
    <div style={{ background: 'linear-gradient(90deg,transparent,rgba(167,139,250,.07),transparent)', borderBottom: '1px solid rgba(167,139,250,.12)', textAlign: 'center', padding: '9px 16px', fontSize: 12, color: '#a78bfa', fontWeight: 500, letterSpacing: '.04em' }}>
      <em style={{ color: 'var(--pink)', fontStyle: 'normal', fontWeight: 700, marginRight: 4 }}>✦ NEW</em>
      Vortex supports web search, multi-model routing &amp; persistent memory —{' '}
      <a href="#" style={{ color: '#c4b5fd' }}>Changelog →</a>
    </div>
  )
}

const PRISM_NAV = (
  <svg width="24" height="24" viewBox="0 0 80 80" fill="none">
    <defs>
      <linearGradient id="ng" x1="12" y1="8" x2="68" y2="72" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#f472b6"/>
        <stop offset="50%" stopColor="#a78bfa"/>
        <stop offset="100%" stopColor="#60a5fa"/>
      </linearGradient>
    </defs>
    <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="url(#ng)" strokeWidth="2.5"/>
    <line x1="40" y1="8" x2="68" y2="40" stroke="#f472b6" strokeWidth="1.5" opacity=".5"/>
    <line x1="40" y1="8" x2="40" y2="72" stroke="#a78bfa" strokeWidth="1.5" opacity=".5"/>
    <line x1="40" y1="8" x2="12" y2="40" stroke="#60a5fa" strokeWidth="1.5" opacity=".5"/>
    <circle cx="40" cy="40" r="4" fill="#e0d7ff"/>
  </svg>
)

function VortexNav() {
  return (
    <nav style={{ position: 'sticky', top: 0, zIndex: 100, display: 'flex', alignItems: 'center', padding: '0 56px', height: 60, background: 'rgba(4,4,7,.85)', backdropFilter: 'blur(20px)', borderBottom: '1px solid rgba(22,22,40,.8)' }}>
      <a href="/" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
        {PRISM_NAV}
        <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-.04em', background: 'linear-gradient(90deg,var(--pink),var(--violet))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>Vortex</span>
      </a>
      <ul style={{ display: 'flex', gap: 32, marginLeft: 40, listStyle: 'none' }}>
        {['Features','Docs','Blog'].map(l => (
          <li key={l}><a href="#" style={{ color: '#4b5563', textDecoration: 'none', fontSize: 14, fontWeight: 500 }}>{l}</a></li>
        ))}
      </ul>
      <div style={{ marginLeft: 'auto', display: 'flex', gap: 10, alignItems: 'center' }}>
        <a href={`${getAppUrl()}/login`} style={{ padding: '7px 18px', background: 'transparent', border: '1px solid var(--b2)', color: '#4b5563', fontSize: 13, fontWeight: 500, borderRadius: 7, textDecoration: 'none' }}>Sign in</a>
        <a href={`${getAppUrl()}/register`} style={{ padding: '8px 20px', background: 'linear-gradient(135deg,#f472b6,#a78bfa 60%,#60a5fa)', color: '#fff', fontSize: 13, fontWeight: 600, borderRadius: 7, textDecoration: 'none', boxShadow: '0 0 20px rgba(167,139,250,.25)' }}>Get started</a>
      </div>
    </nav>
  )
}

function VortexFooter() {
  const cols = [
    { head: 'Product',    links: ['Chat','Knowledge Bases','Memory','Changelog'] },
    { head: 'Developers', links: ['Docs','API','GitHub','Self-hosting'] },
    { head: 'Company',    links: ['About','Blog','Privacy','Terms'] },
  ]
  return (
    <footer style={{ background: '#020205', borderTop: '1px solid var(--border)', padding: '56px 56px 32px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 48, marginBottom: 48 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <svg width="18" height="18" viewBox="0 0 80 80" fill="none"><polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="#a78bfa" strokeWidth="3"/><circle cx="40" cy="40" r="4" fill="#a78bfa"/></svg>
            <span style={{ fontSize: 15, fontWeight: 700, background: 'linear-gradient(90deg,var(--pink),var(--violet))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>Vortex</span>
          </div>
          <p style={{ fontSize: 13, color: 'var(--dim)', lineHeight: 1.7, maxWidth: 240 }}>The AI portal for teams. Chat, search, remember — all in one place.</p>
        </div>
        {cols.map(c => (
          <div key={c.head}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--dim)', marginBottom: 16 }}>{c.head}</div>
            <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 11 }}>
              {c.links.map(l => <li key={l}><a href="#" style={{ fontSize: 13, color: '#1e1e35', textDecoration: 'none' }}>{l}</a></li>)}
            </ul>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 24, borderTop: '1px solid var(--border)', fontSize: 12, color: 'var(--dim)' }}>
        <span>© 2026 Vortex. All rights reserved.</span>
        <span>Built with ♥ and Claude</span>
      </div>
    </footer>
  )
}
```

- [ ] **Step 3: Verify dev server starts**

```bash
cd landing && pnpm dev --host
```
Expected: server on http://localhost:5174 with dark background, Vortex nav visible.

- [ ] **Step 4: Commit**

```bash
git add landing/src/routes/__root.tsx
git commit -m "feat(landing): Vortex nav, footer, and announce bar"
```

---

## Task 3: Hero Section (static structure)

**Files:**
- Create: `landing/src/components/HeroSection.tsx`
- Modify: `landing/src/routes/index.tsx`

- [ ] **Step 1: Create HeroSection.tsx**

```tsx
// landing/src/components/HeroSection.tsx
import * as React from 'react'

const PRISM_SVG_SMALL = (
  <svg width="18" height="18" viewBox="0 0 80 80" fill="none">
    <defs><linearGradient id="sg" x1="12" y1="8" x2="68" y2="72" gradientUnits="userSpaceOnUse"><stop offset="0%" stopColor="#f472b6"/><stop offset="50%" stopColor="#a78bfa"/><stop offset="100%" stopColor="#60a5fa"/></linearGradient></defs>
    <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="url(#sg)" strokeWidth="3"/>
    <circle cx="40" cy="40" r="4" fill="#a78bfa"/>
  </svg>
)

const SEND_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" width="14" height="14">
    <line x1="22" y1="2" x2="11" y2="13"/>
    <polygon points="22 2 15 22 11 13 2 9 22 2"/>
  </svg>
)

const CHAT_ICON = (w = 14) => (
  <svg style={{ width: w, height: w, opacity: .6 }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
  </svg>
)

const KB_ICON = (w = 14) => (
  <svg style={{ width: w, height: w, opacity: .6 }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
    <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
  </svg>
)

export function HeroSection() {
  const threadRef    = React.useRef<HTMLDivElement>(null)
  const composerRef  = React.useRef<HTMLTextAreaElement>(null)
  const charCountRef = React.useRef<HTMLSpanElement>(null)
  const sendBtnRef   = React.useRef<HTMLButtonElement>(null)

  React.useEffect(() => {
    let cleanup: (() => void) | undefined
    // Lazy-import to avoid SSR issues
    import('~/lib/demo-hero').then(({ startHeroDemo }) => {
      if (!threadRef.current || !composerRef.current || !charCountRef.current || !sendBtnRef.current) return
      cleanup = startHeroDemo({
        thread:    threadRef.current,
        composer:  composerRef.current,
        charCount: charCountRef.current,
        sendBtn:   sendBtnRef.current,
      })
    })
    return () => cleanup?.()
  }, [])

  return (
    <section style={{ position: 'relative', overflow: 'hidden', minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '100px 24px 60px' }}>
      {/* Background */}
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
        <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse 80% 60% at 50% 20%,rgba(167,139,250,.07) 0%,transparent 70%),radial-gradient(ellipse 50% 40% at 20% 80%,rgba(244,114,182,.04) 0%,transparent 60%),radial-gradient(ellipse 50% 40% at 80% 80%,rgba(96,165,250,.04) 0%,transparent 60%)', animation: 'bgBreath 8s ease-in-out infinite' }}/>
        <div style={{ position: 'absolute', inset: 0, backgroundImage: 'linear-gradient(rgba(167,139,250,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(167,139,250,.03) 1px,transparent 1px)', backgroundSize: '64px 64px', maskImage: 'radial-gradient(ellipse 80% 80% at 50% 50%,black 30%,transparent 100%)', WebkitMaskImage: 'radial-gradient(ellipse 80% 80% at 50% 50%,black 30%,transparent 100%)' }}/>
      </div>

      {/* Content */}
      <div style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%', maxWidth: 1000 }}>

        {/* Badge */}
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '5px 14px 5px 8px', background: 'rgba(167,139,250,.06)', border: '1px solid rgba(167,139,250,.18)', borderRadius: 100, fontSize: 12, color: '#a78bfa', fontWeight: 500, fontFamily: 'monospace', marginBottom: 40, animation: 'fadeDown .7s ease both' }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#22c55e', animation: 'dotPulse 2s ease-in-out infinite' }}/>
          prod server&nbsp;&nbsp;<span style={{ color: '#2a2a3e' }}>/</span>&nbsp;&nbsp;running
        </div>

        <p style={{ fontSize: 13, fontWeight: 600, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--violet)', marginBottom: 18, animation: 'fadeDown .7s ease .1s both' }}>AI Portal · Built for Teams</p>

        <h1 style={{ fontSize: 'clamp(40px,6vw,76px)', fontWeight: 900, letterSpacing: '-.055em', lineHeight: .95, textAlign: 'center', marginBottom: 24, animation: 'fadeUp .8s ease .2s both' }}>
          <span style={{ display: 'block', color: 'var(--text)' }}>Ask anything.</span>
          <span style={{ display: 'block', margin: '6px 0' }}>
            <span style={{ background: 'linear-gradient(100deg,var(--pink) 0%,var(--violet) 45%,var(--blue) 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', backgroundSize: '400% 100%', backgroundPosition: '100% 0', animation: 'shineSweep 5s ease-in-out .8s forwards' }}>
              Know everything.
            </span>
          </span>
          <span style={{ display: 'block', color: 'rgba(232,228,255,.28)', fontWeight: 800 }}>Ship faster.</span>
        </h1>

        <p style={{ fontSize: 18, color: 'var(--muted)', maxWidth: 500, lineHeight: 1.7, textAlign: 'center', marginBottom: 40, animation: 'fadeUp .8s ease .35s both' }}>
          Stop switching between AI tools and repeating context.{' '}
          <strong style={{ color: '#94a3b8', fontWeight: 500 }}>Vortex connects the best models to your knowledge, memory, and team</strong> — in one place.
        </p>

        <div style={{ display: 'flex', gap: 14, alignItems: 'center', justifyContent: 'center', flexWrap: 'wrap', marginBottom: 60, animation: 'fadeUp .8s ease .5s both' }}>
          <a href="#" style={{ padding: '14px 32px', background: 'linear-gradient(135deg,var(--pink),var(--violet) 60%,var(--blue))', color: '#fff', fontSize: 15, fontWeight: 700, borderRadius: 10, border: 'none', textDecoration: 'none', letterSpacing: '-.01em', boxShadow: '0 4px 32px rgba(167,139,250,.3)' }}>Start for free →</a>
          <a href="#hiw" style={{ padding: '14px 28px', background: 'transparent', border: '1px solid var(--b2)', color: '#4b5563', fontSize: 15, fontWeight: 500, borderRadius: 10, textDecoration: 'none' }}>See how it works</a>
        </div>

        {/* App demo frame */}
        <div style={{ width: '100%', maxWidth: 960, animation: 'fadeUp .9s ease .65s both' }}>
          <div style={{ background: '#0a0a12', border: '1px solid rgba(167,139,250,.12)', borderRadius: 16, overflow: 'hidden', boxShadow: '0 48px 120px rgba(0,0,0,.85),0 0 80px rgba(167,139,250,.05)' }}>
            {/* Title bar */}
            <div style={{ background: '#0c0c18', borderBottom: '1px solid var(--border)', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 8 }}>
              {[0,1,2].map(i => <div key={i} style={{ width: 8, height: 8, borderRadius: '50%', background: '#2a2a3e' }}/>)}
              <div style={{ marginLeft: 12, flex: 1, background: '#111122', border: '1px solid var(--border)', borderRadius: 5, padding: '4px 10px', fontSize: 11, color: '#374151', fontFamily: 'monospace' }}>vortex.app/chat/conversations/42</div>
            </div>

            {/* App shell */}
            <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', height: 520 }}>
              {/* Sidebar */}
              <div style={{ background: '#060610', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                <div style={{ padding: '14px 14px 10px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
                  {PRISM_SVG_SMALL}
                  <span style={{ fontSize: 14, fontWeight: 700, letterSpacing: '-.03em', background: 'linear-gradient(90deg,var(--pink),var(--violet))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>Vortex</span>
                </div>
                <div style={{ padding: '8px 0', flex: 1 }}>
                  {[
                    { label: 'Conversations', isSection: true },
                    { label: 'Q3 Risk Analysis', active: true },
                    { label: 'Product roadmap 2026' },
                    { label: 'Engineering runbook' },
                    { label: 'Knowledge Bases', isSection: true },
                    { label: 'Finance Docs', isKb: true },
                    { label: 'Product Specs', isKb: true },
                  ].map((item, i) => item.isSection
                    ? <div key={i} style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: '#1e1e35', padding: '6px 14px 4px', marginTop: i > 0 ? 8 : 0 }}>{item.label}</div>
                    : <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 14px', fontSize: 12, color: item.active ? '#c4b5fd' : '#374151', background: item.active ? 'rgba(167,139,250,.08)' : 'transparent' }}>
                        {item.isKb ? KB_ICON() : CHAT_ICON()}
                        {item.label}
                      </div>
                  )}
                </div>
              </div>

              {/* Chat */}
              <div style={{ display: 'flex', flexDirection: 'column', background: '#07070e' }}>
                <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#6b7280' }}>Q3 Risk Analysis</span>
                  <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5, padding: '3px 8px', background: 'rgba(167,139,250,.06)', border: '1px solid rgba(167,139,250,.12)', borderRadius: 5, fontSize: 10, color: '#a78bfa', fontFamily: 'monospace' }}>
                    <svg viewBox="0 0 80 80" fill="none" width="10" height="10"><polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="#a78bfa" strokeWidth="4"/></svg>
                    claude-sonnet-4-6
                  </div>
                </div>

                <div ref={threadRef} style={{ flex: 1, overflowY: 'auto', padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 16 }}/>

                {/* Composer */}
                <div style={{ borderTop: '1px solid var(--border)', padding: '10px 14px', background: '#060610' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, flexWrap: 'wrap' }}>
                    <span className="cap-tag cap-reflection">
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9.5 2a9 9 0 0 1 0 18 4.5 4.5 0 0 1 0-9"/><path d="M11.5 11.5h8"/></svg>
                      Reflection
                    </span>
                    <span className="cap-tag cap-research">
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
                      Research
                    </span>
                    <span className="kb-tag">
                      {KB_ICON(10)}
                      Finance Docs
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
                    <textarea ref={composerRef} className="composer-textarea" placeholder="Message Vortex…" rows={1} readOnly/>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center' }}>
                      <div style={{ fontSize: 10, color: '#374151', fontFamily: 'monospace', border: '1px solid var(--border)', background: '#0a0a18', borderRadius: 5, padding: '3px 6px' }}>claude-sonnet-4-6 ▾</div>
                      <button ref={sendBtnRef} style={{ width: 32, height: 32, borderRadius: 8, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg,var(--pink),var(--violet))', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        {SEND_ICON}
                      </button>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
                    <span style={{ fontSize: 10, color: '#2a2a3e', padding: '2px 6px', border: '1px solid var(--border)', borderRadius: 4 }}>📎 Attach</span>
                    <span ref={charCountRef} style={{ fontSize: 10, color: '#1e1e35', marginLeft: 'auto' }}>0 / 2000</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
```

- [ ] **Step 2: Update `index.tsx` to use HeroSection**

```tsx
// landing/src/routes/index.tsx
import { createFileRoute } from '@tanstack/react-router'
import { HeroSection } from '~/components/HeroSection'

export const Route = createFileRoute('/')({
  component: HomePage,
})

function HomePage() {
  return (
    <>
      <HeroSection />
    </>
  )
}
```

- [ ] **Step 3: Verify hero renders**

```bash
cd landing && pnpm dev --host
```
Navigate to http://localhost:5174. Expected: dark hero with gradient headline, app demo frame visible. Animation not running yet (demo-hero.ts doesn't exist yet).

- [ ] **Step 4: Commit**

```bash
git add landing/src/components/HeroSection.tsx landing/src/routes/index.tsx
git commit -m "feat(landing): hero section static structure"
```

---

## Task 4: Hero Animation Module

**Files:**
- Create: `landing/src/lib/demo-hero.ts`

- [ ] **Step 1: Create demo-hero.ts**

```typescript
// landing/src/lib/demo-hero.ts

const USER_MSG = "What were the key risks from our Q3 report, and how should we address them in Q4 planning?"

const AI_RESPONSE = `Based on your Q3 report and Q4 planning brief, three critical risks stand out:

**1. Customer concentration** — top 3 customers represent 42% of ARR, with renewals clustering in Q1. Q4 is your window to lock in expansions before renewal pressure hits.

**2. Margin compression** — $42M R&D spend is up 34% YoY. The board needs a clear ROI story by December 15. Prepare the narrative now.

**3. Infrastructure overage** — cloud costs are tracking $2.1M above budget. Migrating to reserved instances can recover ~$800K before year-end.`

// SVG strings — kept as template literals to avoid React dependency in this module
const PRISM_SVG   = `<svg viewBox="0 0 80 80" fill="none" width="10" height="10" style="animation:prismSpin 1s linear infinite"><polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="currentColor" stroke-width="5"/></svg>`
const CHECK_SVG   = `<svg style="color:#22c55e;width:10px;height:10px" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`
const BRAIN_SVG   = `<svg style="width:12px;height:12px;flex-shrink:0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9.5 2a9 9 0 0 1 0 18 4.5 4.5 0 0 1 0-9"/><path d="M11.5 11.5h8"/></svg>`
const LIB_SVG     = `<svg style="width:12px;height:12px;flex-shrink:0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>`
const CHEV_SVG    = `<svg style="width:10px;height:10px;opacity:.4;flex-shrink:0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>`
const AI_AVATAR   = `<svg viewBox="0 0 80 80" fill="none" width="14" height="14"><polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="white" stroke-width="5"/></svg>`

export interface HeroDemoRefs {
  thread:    HTMLElement
  composer:  HTMLTextAreaElement
  charCount: HTMLElement
  sendBtn:   HTMLElement
}

function sleep(ms: number): Promise<void> {
  return new Promise(r => setTimeout(r, ms))
}

function addEl(thread: HTMLElement, html: string): HTMLElement {
  const div = document.createElement('div')
  div.innerHTML = html
  const el = div.firstElementChild as HTMLElement
  el.style.cssText = 'opacity:0;transform:translateY(8px);transition:opacity .4s ease,transform .4s ease'
  thread.appendChild(el)
  requestAnimationFrame(() => requestAnimationFrame(() => {
    el.style.opacity = '1'
    el.style.transform = 'none'
  }))
  thread.scrollTop = thread.scrollHeight
  return el
}

async function typeInComposer(composer: HTMLTextAreaElement, charCount: HTMLElement, text: string): Promise<void> {
  composer.value = ''
  for (let i = 0; i <= text.length; i++) {
    composer.value = text.slice(0, i)
    charCount.textContent = `${i} / 2000`
    await sleep(26 + Math.random() * 18)
  }
}

async function streamText(el: HTMLElement, thread: HTMLElement, text: string): Promise<void> {
  let built = ''
  for (const ch of text) {
    built += ch
    el.innerHTML = built.replace(/\*\*(.*?)\*\*/g, '<strong style="color:#e8e4ff">$1</strong>') + '<span class="cursor"></span>'
    thread.scrollTop = thread.scrollHeight
    await sleep(ch === ' ' ? 16 : ch === '\n' ? 55 : 20)
  }
  el.innerHTML = built.replace(/\*\*(.*?)\*\*/g, '<strong style="color:#e8e4ff">$1</strong>')
}

async function runOnce(refs: HeroDemoRefs, stopped: { value: boolean }): Promise<void> {
  const { thread, composer, charCount, sendBtn } = refs
  if (stopped.value) return

  await sleep(1000)
  if (stopped.value) return

  await typeInComposer(composer, charCount, USER_MSG)
  await sleep(450)
  if (stopped.value) return

  sendBtn.style.transform = 'scale(0.9)'
  await sleep(100)
  sendBtn.style.transform = ''
  composer.value = ''
  charCount.textContent = '0 / 2000'

  addEl(thread, `<div class="msg-user"><div class="msg-user-bubble">${USER_MSG}</div></div>`)
  await sleep(280)
  if (stopped.value) return

  // Chips row
  const chipsRow = addEl(thread, `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:4px"></div>`)
  const memChip = document.createElement('div')
  memChip.className = 'chip chip-memory'
  memChip.innerHTML = `${BRAIN_SVG}<span>Loading memories…</span>${PRISM_SVG}`
  chipsRow.appendChild(memChip)
  await sleep(950)
  if (stopped.value) return

  memChip.innerHTML = `${BRAIN_SVG}<span>3 memories loaded</span>${CHECK_SVG}`
  await sleep(180)

  const kbChip = document.createElement('div')
  kbChip.className = 'chip chip-kb'
  kbChip.style.cssText = 'opacity:0;transform:translateY(6px);transition:opacity .3s,transform .3s'
  kbChip.innerHTML = `${LIB_SVG}<span>Searching KB…</span>${PRISM_SVG}`
  chipsRow.appendChild(kbChip)
  requestAnimationFrame(() => requestAnimationFrame(() => {
    kbChip.style.opacity = '1'
    kbChip.style.transform = 'none'
  }))
  await sleep(1050)
  if (stopped.value) return

  kbChip.innerHTML = `${LIB_SVG}<span>KB Searched "Q3 risks Q4 planning"</span>${CHECK_SVG}${CHEV_SVG}`
  await sleep(280)

  // Thinking dots
  const thinkEl = addEl(thread, `<div style="display:flex;align-items:center;gap:5px;padding:8px 12px"><div class="thinking-dot"></div><div class="thinking-dot" style="animation-delay:.18s"></div><div class="thinking-dot" style="animation-delay:.36s"></div></div>`)
  await sleep(820)
  if (stopped.value) return
  thread.removeChild(thinkEl)

  // AI response
  const aiMsg = addEl(thread, `<div class="msg-ai"><div class="msg-ai-avatar">${AI_AVATAR}</div><div class="msg-ai-body"><div class="msg-ai-name">Vortex · claude-sonnet-4-6</div><div class="msg-ai-text"></div></div></div>`)
  const aiText = aiMsg.querySelector('.msg-ai-text') as HTMLElement
  if (stopped.value) return
  await streamText(aiText, thread, AI_RESPONSE)

  await sleep(380)
  if (stopped.value) return
  addEl(thread, `<div style="display:flex;align-items:center;gap:6px;padding:6px 10px;background:rgba(59,7,100,.15);border:1px solid rgba(126,34,206,.15);border-radius:8px;font-size:11px;color:#a78bfa;margin-top:4px">${LIB_SVG}<span>Used: Finance Docs (3 chunks), Q4 Planning Brief (1 chunk)</span></div>`)

  await sleep(6000)
  if (stopped.value) return
  thread.innerHTML = ''
  runOnce(refs, stopped)
}

export function startHeroDemo(refs: HeroDemoRefs): () => void {
  const stopped = { value: false }
  runOnce(refs, stopped)
  return () => { stopped.value = true }
}
```

- [ ] **Step 2: Verify hero animation plays**

```bash
cd landing && pnpm dev --host
```
Navigate to http://localhost:5174. Expected: text types into composer, sends, chips animate (memory blue → KB purple), thinking dots, AI response streams word-by-word, loops after pause.

- [ ] **Step 3: Commit**

```bash
git add landing/src/lib/demo-hero.ts
git commit -m "feat(landing): hero chat animation sequence"
```

---

## Task 5: Logo Band + Scroll Reveal Hook

**Files:**
- Create: `landing/src/components/LogoBand.tsx`
- Create: `landing/src/hooks/useScrollReveal.ts`
- Modify: `landing/src/routes/index.tsx`

- [ ] **Step 1: Create useScrollReveal.ts**

```typescript
// landing/src/hooks/useScrollReveal.ts
import { useEffect, useRef } from 'react'

export function useScrollReveal<T extends HTMLElement>(
  options?: IntersectionObserverInit
) {
  const ref = useRef<T>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.classList.add('visible')
          obs.unobserve(el)
        }
      },
      { threshold: 0.1, rootMargin: '0px 0px -40px 0px', ...options }
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  return ref
}
```

- [ ] **Step 2: Create LogoBand.tsx**

```tsx
// landing/src/components/LogoBand.tsx
import * as React from 'react'
import { useScrollReveal } from '~/hooks/useScrollReveal'

const LOGOS = ['Anthropic','OpenAI','Vercel','Linear','Notion','Stripe','Cloudflare','Figma']

export function LogoBand() {
  const ref = useScrollReveal<HTMLDivElement>()
  const track = [...LOGOS, ...LOGOS] // double for seamless loop

  return (
    <div ref={ref} className="reveal" style={{ padding: '40px 0', overflow: 'hidden' }}>
      <div style={{ textAlign: 'center', fontSize: 11, letterSpacing: '.14em', textTransform: 'uppercase', color: '#1e1e35', fontWeight: 700, marginBottom: 22 }}>
        Trusted by teams at
      </div>
      <div style={{ overflow: 'hidden', WebkitMaskImage: 'linear-gradient(90deg,transparent,black 12%,black 88%,transparent)', maskImage: 'linear-gradient(90deg,transparent,black 12%,black 88%,transparent)' }}>
        <div style={{ display: 'flex', gap: 52, width: 'max-content', animation: 'ticker 22s linear infinite', alignItems: 'center' }}>
          {track.map((name, i) => (
            <span key={i} style={{ fontSize: 13, fontWeight: 700, color: '#1e1e35', whiteSpace: 'nowrap' }}>{name}</span>
          ))}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Add LogoBand to index.tsx**

```tsx
// landing/src/routes/index.tsx
import { createFileRoute } from '@tanstack/react-router'
import { HeroSection } from '~/components/HeroSection'
import { LogoBand } from '~/components/LogoBand'

export const Route = createFileRoute('/')({
  component: HomePage,
})

function HomePage() {
  return (
    <>
      <HeroSection />
      <div className="section-divider"/>
      <LogoBand />
      <div className="section-divider"/>
    </>
  )
}
```

- [ ] **Step 4: Commit**

```bash
git add landing/src/hooks/useScrollReveal.ts landing/src/components/LogoBand.tsx landing/src/routes/index.tsx
git commit -m "feat(landing): logo band marquee and scroll reveal hook"
```

---

## Task 6: How It Works — Chip Animation Module

**Files:**
- Create: `landing/src/lib/demo-chips.ts`

- [ ] **Step 1: Create demo-chips.ts**

```typescript
// landing/src/lib/demo-chips.ts

const PREVIEW = "Based on your Q3 report, three critical risks stand out for Q4: customer concentration (42% ARR in top 3 accounts), margin compression ($42M R&D up 34% YoY), and infrastructure overage ($2.1M over budget). Here's the Q4 action plan…"

const PRISM_SVG = `<svg viewBox="0 0 80 80" fill="none" width="10" height="10" style="animation:prismSpin 1s linear infinite"><polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="currentColor" stroke-width="5"/></svg>`
const CHECK_SVG = `<svg style="color:#22c55e;width:10px;height:10px" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`
const BRAIN_SVG = `<svg style="width:12px;height:12px;flex-shrink:0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9.5 2a9 9 0 0 1 0 18 4.5 4.5 0 0 1 0-9"/><path d="M11.5 11.5h8"/></svg>`
const LIB_SVG   = `<svg style="width:12px;height:12px;flex-shrink:0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>`
const CHEV_SVG  = `<svg style="width:10px;height:10px;opacity:.4;flex-shrink:0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>`

export interface ChipDemoRefs {
  row:      HTMLElement
  thinkRow: HTMLElement
  respEl:   HTMLElement
  txtEl:    HTMLElement
  labelEl:  HTMLElement
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((res, rej) => {
    const t = setTimeout(res, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(t)
      rej(new DOMException('Aborted', 'AbortError'))
    })
  })
}

export async function runChipDemo(refs: ChipDemoRefs, signal: AbortSignal): Promise<void> {
  const { row, thinkRow, respEl, txtEl, labelEl } = refs

  try {
    // Reset
    row.innerHTML        = ''
    thinkRow.style.display = 'none'
    respEl.style.display   = 'none'
    txtEl.textContent      = ''
    labelEl.textContent    = 'vortex · processing…'

    await sleep(600, signal)

    // Memory chip
    const mem = document.createElement('div')
    mem.className = 'chip chip-memory'
    mem.style.cssText = 'opacity:0;transform:translateY(6px);transition:opacity .3s,transform .3s'
    mem.innerHTML = `${BRAIN_SVG}<span>Loading memories…</span>${PRISM_SVG}`
    row.appendChild(mem)
    await sleep(40, signal)
    mem.style.opacity = '1'
    mem.style.transform = 'none'
    await sleep(1000, signal)
    mem.innerHTML = `${BRAIN_SVG}<span>3 memories loaded</span>${CHECK_SVG}`
    await sleep(220, signal)

    // KB chip
    const kb = document.createElement('div')
    kb.className = 'chip chip-kb'
    kb.style.cssText = 'opacity:0;transform:translateY(6px);transition:opacity .3s,transform .3s'
    kb.innerHTML = `${LIB_SVG}<span>Searching knowledge base…</span>${PRISM_SVG}`
    row.appendChild(kb)
    await sleep(40, signal)
    kb.style.opacity = '1'
    kb.style.transform = 'none'
    await sleep(1100, signal)
    kb.innerHTML = `${LIB_SVG}<span>KB Searched "Q3 risks Q4 planning"</span>${CHECK_SVG}${CHEV_SVG}`
    labelEl.textContent = 'vortex · thinking…'
    await sleep(300, signal)

    // Thinking dots
    thinkRow.style.display = 'flex'
    await sleep(900, signal)
    thinkRow.style.display = 'none'

    // Stream response
    labelEl.textContent      = 'vortex · streaming…'
    respEl.style.display     = 'flex'
    respEl.style.opacity     = '0'
    respEl.style.transition  = 'opacity .4s'
    await sleep(30, signal)
    respEl.style.opacity = '1'

    let built = ''
    for (const ch of PREVIEW) {
      if (signal.aborted) return
      built += ch
      txtEl.innerHTML = built + '<span class="cursor"></span>'
      await sleep(ch === ' ' ? 16 : ch === ',' || ch === '.' ? 45 : 18, signal)
    }
    txtEl.innerHTML     = built
    labelEl.textContent = 'vortex · done'

  } catch (e) {
    if ((e as DOMException).name !== 'AbortError') throw e
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add landing/src/lib/demo-chips.ts
git commit -m "feat(landing): Process tab chip animation module"
```

---

## Task 7: How It Works — Full Tabbed Section

**Files:**
- Create: `landing/src/components/HowItWorks.tsx`
- Modify: `landing/src/routes/index.tsx`

- [ ] **Step 1: Create HowItWorks.tsx**

```tsx
// landing/src/components/HowItWorks.tsx
import * as React from 'react'
import { runChipDemo, type ChipDemoRefs } from '~/lib/demo-chips'

const TAB_DURATIONS = [5000, 11000, 5000, 5000]

const TABS = [
  { step: 'Step 01', label: 'Compose',   sub: 'Pick model, attach KB' },
  { step: 'Step 02', label: 'Process',   sub: 'Memory, KB, web search' },
  { step: 'Step 03', label: 'Knowledge', sub: 'Grounded, cited answers' },
  { step: 'Step 04', label: 'Memory',    sub: 'Learns from every session' },
]

// ─── Shared icon SVGs ────────────────────────────────────────────────────────
const LIB_ICON = (size = 10) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
    <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
  </svg>
)
const BRAIN_ICON = (size = 10) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M9.5 2a9 9 0 0 1 0 18 4.5 4.5 0 0 1 0-9"/>
    <path d="M11.5 11.5h8"/>
  </svg>
)
const CHECK_ICON = (
  <svg style={{ color: '#22c55e', width: 10, height: 10 }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
)
const CHEV_DOWN = (
  <svg style={{ width: 10, height: 10, opacity: .4 }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="6 9 12 15 18 9"/>
  </svg>
)
const SEND_BTN_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" width="12" height="12">
    <line x1="22" y1="2" x2="11" y2="13"/>
    <polygon points="22 2 15 22 11 13 2 9 22 2"/>
  </svg>
)

// ─── Step text column ─────────────────────────────────────────────────────────
function StepText({ n, tag, title, accent, accentColor, desc, bullets }: {
  n: string; tag: string; title: React.ReactNode; accent?: string; accentColor?: string
  desc: string; bullets: string[]
}) {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <span style={{ width: 24, height: 24, borderRadius: 6, background: 'rgba(167,139,250,.1)', border: '1px solid rgba(167,139,250,.2)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color: 'var(--violet)', flexShrink: 0 }}>{n}</span>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--dim)' }}>{tag}</span>
      </div>
      <h3 style={{ fontSize: 'clamp(20px,2.4vw,30px)', fontWeight: 700, letterSpacing: '-.035em', lineHeight: 1.2, marginBottom: 14 }}>{title}</h3>
      <p style={{ fontSize: 15, color: 'var(--muted)', lineHeight: 1.75, marginBottom: 18, maxWidth: 400 }}>{desc}</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {bullets.map((b, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13, color: '#374151', lineHeight: 1.5 }}>
            <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--violet)', flexShrink: 0, marginTop: 5, opacity: .5 }}/>
            {b}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Demo bar ─────────────────────────────────────────────────────────────────
function DemoBar({ label }: { label: string }) {
  return (
    <div style={{ background: '#0c0c1a', padding: '9px 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 5 }}>
      {[0,1,2].map(i => <div key={i} style={{ width: 7, height: 7, borderRadius: '50%', background: '#2a2a3e' }}/>)}
      <span style={{ fontSize: 10, color: '#2a2a3e', marginLeft: 8, fontFamily: 'monospace' }}>{label}</span>
    </div>
  )
}

// ─── Panel 0: Compose ────────────────────────────────────────────────────────
function Panel0() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 72, alignItems: 'center', padding: '64px 56px', animation: 'panelIn .4s ease both' }}>
      <StepText
        n="1" tag="Compose"
        title={<>Any question.<br/><span style={{ color: 'var(--violet)' }}>Any model.</span></>}
        desc="Pick Claude, GPT-4o, or Gemini. Toggle Research mode for web search, Reflection for deeper reasoning. Attach a knowledge base with one click."
        bullets={['10+ models in one interface','Research + Reflection capability toggles','Attach files or knowledge bases inline']}
      />
      <div style={{ background: '#060610', border: '1px solid rgba(167,139,250,.1)', borderRadius: 14, overflow: 'hidden', boxShadow: '0 24px 60px rgba(0,0,0,.5)' }}>
        <DemoBar label="composer · claude-sonnet-4-6"/>
        <div style={{ padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
            <span className="cap-tag cap-reflection">{BRAIN_ICON()} Reflection</span>
            <span className="cap-tag cap-research">{LIB_ICON()} Research</span>
            <span className="kb-tag">{LIB_ICON()} Finance Docs <span style={{ fontSize: 9, background: 'rgba(167,139,250,.15)', borderRadius: 3, padding: '0 4px', marginLeft: 2 }}>1</span></span>
          </div>
          <div style={{ background: '#0a0a18', border: '1px solid rgba(167,139,250,.15)', borderRadius: 9, padding: '10px 12px', fontSize: 12, color: '#c4b5fd', lineHeight: 1.6, minHeight: 48 }}>
            What were the key risks from our Q3 report, and how should we address them in Q4 planning?<span className="cursor"/>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
            <span style={{ fontSize: 10, color: '#2a2a3e', padding: '3px 8px', border: '1px solid var(--border)', borderRadius: 4 }}>📎</span>
            <span style={{ fontSize: 10, color: '#374151', fontFamily: 'monospace', border: '1px solid var(--border)', padding: '3px 8px', borderRadius: 4 }}>claude-sonnet-4-6 ▾</span>
            <div style={{ width: 28, height: 28, borderRadius: 8, border: 'none', background: 'linear-gradient(135deg,var(--pink),var(--violet))', display: 'flex', alignItems: 'center', justifyContent: 'center', marginLeft: 'auto' }}>{SEND_BTN_ICON}</div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Panel 1: Process (animated) ─────────────────────────────────────────────
function Panel1({ active }: { active: boolean }) {
  const rowRef     = React.useRef<HTMLDivElement>(null)
  const thinkRef   = React.useRef<HTMLDivElement>(null)
  const respRef    = React.useRef<HTMLDivElement>(null)
  const txtRef     = React.useRef<HTMLDivElement>(null)
  const labelRef   = React.useRef<HTMLSpanElement>(null)
  const jobRef     = React.useRef<AbortController | null>(null)

  React.useEffect(() => {
    if (!active) {
      jobRef.current?.abort()
      jobRef.current = null
      return
    }
    if (!rowRef.current || !thinkRef.current || !respRef.current || !txtRef.current || !labelRef.current) return
    const ac = new AbortController()
    jobRef.current = ac
    const refs: ChipDemoRefs = {
      row:      rowRef.current,
      thinkRow: thinkRef.current,
      respEl:   respRef.current,
      txtEl:    txtRef.current,
      labelEl:  labelRef.current,
    }
    runChipDemo(refs, ac.signal)
    return () => { ac.abort(); jobRef.current = null }
  }, [active])

  const AI_AVATAR_SVG = `<svg viewBox="0 0 80 80" fill="none" width="14" height="14"><polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="white" stroke-width="5"/></svg>`

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 72, alignItems: 'center', padding: '64px 56px', animation: 'panelIn .4s ease both' }}>
      {/* Demo left */}
      <div style={{ background: '#060610', border: '1px solid rgba(167,139,250,.1)', borderRadius: 14, overflow: 'hidden', boxShadow: '0 24px 60px rgba(0,0,0,.5)' }}>
        <DemoBar label={<span ref={labelRef as any}>vortex · waiting…</span> as any}/>
        <div style={{ padding: 16 }}>
          <div className="msg-user" style={{ marginBottom: 14 }}>
            <div className="msg-user-bubble">What were the key risks from Q3, and how should we address them in Q4?</div>
          </div>
          <div ref={rowRef} style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 4 }}/>
          <div ref={thinkRef} style={{ display: 'none', alignItems: 'center', gap: 5, padding: '8px 12px' }}>
            <div className="thinking-dot"/>
            <div className="thinking-dot" style={{ animationDelay: '.18s' }}/>
            <div className="thinking-dot" style={{ animationDelay: '.36s' }}/>
          </div>
          <div ref={respRef} className="msg-ai" style={{ display: 'none' }}>
            <div className="msg-ai-avatar" dangerouslySetInnerHTML={{ __html: AI_AVATAR_SVG }}/>
            <div style={{ flex: 1 }}>
              <div className="msg-ai-name">Vortex · claude-sonnet-4-6</div>
              <div ref={txtRef} className="msg-ai-text"/>
            </div>
          </div>
        </div>
      </div>
      {/* Text right */}
      <StepText
        n="2" tag="Process"
        title={<>Memories, knowledge,<br/><span style={{ color: 'var(--violet)' }}>web — all at once.</span></>}
        desc="Before responding, Vortex loads your memories, searches your knowledge base, and optionally searches the web. You see every tool call as it runs — live."
        bullets={['Memory chip loads your personal context','KB search retrieves relevant document chunks','Web search fetches live data when needed','Each chip expands to show sources']}
      />
    </div>
  )
}

// ─── Panel 2: Knowledge ───────────────────────────────────────────────────────
function Panel2() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 72, alignItems: 'center', padding: '64px 56px', animation: 'panelIn .4s ease both' }}>
      <StepText
        n="3" tag="Knowledge"
        title={<>Grounded answers,<br/><span style={{ color: 'var(--violet)' }}>not hallucinations.</span></>}
        desc="Attach knowledge bases to any conversation. Vortex retrieves the most relevant chunks from your documents and cites them — so every answer is traceable."
        bullets={['Unlimited knowledge base size','Semantic search across all documents','Sources shown inline below response']}
      />
      <div style={{ background: '#060610', border: '1px solid rgba(167,139,250,.1)', borderRadius: 14, overflow: 'hidden', boxShadow: '0 24px 60px rgba(0,0,0,.5)' }}>
        <DemoBar label="knowledge bases · 2 active"/>
        <div style={{ padding: 16 }}>
          <div className="chip chip-kb" style={{ marginBottom: 10, cursor: 'pointer', display: 'inline-flex' }}>
            {LIB_ICON(12)} KB Searched "Q3 risks Q4 planning" {CHECK_ICON} {CHEV_DOWN}
          </div>
          <div style={{ padding: 10, background: '#0a0a18', border: '1px solid rgba(126,34,206,.2)', borderRadius: 8, marginBottom: 12 }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'rgba(126,34,206,.6)', marginBottom: 6 }}>Sources</div>
            <div style={{ fontSize: 11, color: '#c4b5fd', marginBottom: 4 }}>Finance Docs <span style={{ color: 'rgba(167,139,250,.4)' }}>· 3 chunks</span></div>
            <div style={{ fontSize: 11, color: '#c4b5fd' }}>Q4 Planning Brief <span style={{ color: 'rgba(167,139,250,.4)' }}>· 1 chunk</span></div>
          </div>
          <div style={{ background: '#0a0a18', border: '1px solid rgba(126,34,206,.2)', borderRadius: 8, padding: 10 }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'rgba(126,34,206,.6)', marginBottom: 8 }}>Used knowledge bases</div>
            {[['Finance Docs','3 chunks'],['Q4 Planning Brief','1 chunk']].map(([name, count]) => (
              <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', background: 'rgba(59,7,100,.2)', borderRadius: 6, marginBottom: 6 }}>
                {LIB_ICON(12)}<span style={{ fontSize: 11, color: '#c4b5fd' }}>{name}</span>
                <span style={{ fontSize: 10, color: 'rgba(167,139,250,.4)', marginLeft: 'auto' }}>{count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Panel 3: Memory ─────────────────────────────────────────────────────────
function Panel3() {
  const MEMORIES = [
    { color: '#f472b6', label: 'preference', text: 'Prefers risk analysis as: problem → window → action. No bullet points.' },
    { color: '#a78bfa', label: 'context',    text: 'Head of Product at Acme Corp. Q4 planning cycle, board deck due Dec 15.', badge: true },
    { color: '#60a5fa', label: 'tools',      text: 'Linear, Notion, Figma daily. Comfortable with Python and SQL.' },
  ]
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 72, alignItems: 'center', padding: '64px 56px', animation: 'panelIn .4s ease both' }}>
      <div style={{ background: '#060610', border: '1px solid rgba(167,139,250,.1)', borderRadius: 14, overflow: 'hidden', boxShadow: '0 24px 60px rgba(0,0,0,.5)' }}>
        <DemoBar label="memories · 3 loaded this session"/>
        <div style={{ padding: 16 }}>
          <div className="chip chip-memory" style={{ marginBottom: 12, display: 'inline-flex' }}>
            {BRAIN_ICON(12)} 3 memories loaded {CHECK_ICON}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {MEMORIES.map(m => (
              <div key={m.label} style={{ background: '#0a0a18', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px', borderLeft: `2px solid ${m.color}` }}>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: m.color, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
                  {m.label}
                  {m.badge && <span style={{ fontSize: 9, padding: '1px 5px', background: 'rgba(34,197,94,.1)', border: '1px solid rgba(34,197,94,.2)', color: '#22c55e', borderRadius: 3, textTransform: 'none', letterSpacing: 0 }}>● new</span>}
                </div>
                <div style={{ fontSize: 12, color: '#6b7280', lineHeight: 1.5 }}>{m.text}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <StepText
        n="4" tag="Memory"
        title={<>Never repeat<br/><span style={{ color: 'var(--pink)' }}>yourself again.</span></>}
        desc="Vortex auto-learns from every conversation — your role, preferences, team context. The next session starts where the last one left off. No setup needed."
        bullets={['Auto-learned from conversation history','Manually editable, pause or delete anytime','Injected automatically into every thread']}
      />
    </div>
  )
}

// ─── Main HowItWorks component ────────────────────────────────────────────────
export function HowItWorks() {
  const [activeTab, setActiveTab] = React.useState(0)
  const sectionRef  = React.useRef<HTMLElement>(null)
  const timerRef    = React.useRef<ReturnType<typeof setTimeout> | null>(null)
  const startedRef  = React.useRef(false)
  const fillRefs    = [
    React.useRef<HTMLDivElement>(null),
    React.useRef<HTMLDivElement>(null),
    React.useRef<HTMLDivElement>(null),
    React.useRef<HTMLDivElement>(null),
  ]

  const activateTab = React.useCallback((idx: number) => {
    // Reset all progress bars
    fillRefs.forEach(ref => {
      if (!ref.current) return
      ref.current.style.transition = 'none'
      ref.current.style.width = '0%'
    })
    // Animate active fill
    const fill = fillRefs[idx].current
    if (fill) {
      requestAnimationFrame(() => requestAnimationFrame(() => {
        fill.style.transition = `width ${TAB_DURATIONS[idx]}ms linear`
        fill.style.width = '100%'
      }))
    }
    setActiveTab(idx)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => activateTab((idx + 1) % 4), TAB_DURATIONS[idx])
  }, [])

  React.useEffect(() => {
    const el = sectionRef.current
    if (!el) return
    const obs = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && !startedRef.current) {
        startedRef.current = true
        obs.unobserve(el)
        activateTab(0)
      }
    }, { threshold: 0.25 })
    obs.observe(el)
    return () => {
      obs.disconnect()
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [activateTab])

  const panels = [<Panel0/>, <Panel1 active={activeTab === 1}/>, <Panel2/>, <Panel3/>]

  return (
    <section ref={sectionRef} id="hiw" style={{ padding: '100px 56px', background: 'var(--bg2)', borderTop: '1px solid var(--border)' }}>
      {/* Header */}
      <div style={{ maxWidth: 600, margin: '0 auto 64px', textAlign: 'center' }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--violet)', marginBottom: 12 }}>How Vortex works</div>
        <h2 style={{ fontSize: 'clamp(28px,4vw,48px)', fontWeight: 800, letterSpacing: '-.04em', lineHeight: 1.1, marginBottom: 14 }}>Your AI gets smarter<br/>every conversation</h2>
        <p style={{ fontSize: 17, color: 'var(--muted)', lineHeight: 1.7 }}>From the moment you ask to the answer that lands — Vortex works across four layers.</p>
      </div>

      {/* Tab bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', maxWidth: 1100, margin: '0 auto', border: '1px solid var(--border)', borderRadius: '14px 14px 0 0', overflow: 'hidden' }}>
        {TABS.map((t, i) => (
          <button
            key={i}
            onClick={() => { if (timerRef.current) clearTimeout(timerRef.current); activateTab(i) }}
            style={{
              position: 'relative', padding: '18px 20px 16px',
              background: activeTab === i ? 'rgba(167,139,250,.05)' : 'transparent',
              border: 'none', borderRight: i < 3 ? '1px solid var(--border)' : 'none',
              cursor: 'pointer', textAlign: 'left', overflow: 'hidden',
              color: activeTab === i ? 'var(--text)' : 'var(--muted)',
              transition: 'background .2s, color .2s',
            }}
          >
            <span style={{ display: 'block', fontSize: 10, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', fontFamily: 'monospace', color: activeTab === i ? 'var(--violet)' : 'var(--dim)', marginBottom: 4 }}>{t.step}</span>
            <span style={{ display: 'block', fontSize: 14, fontWeight: 600 }}>{t.label}</span>
            <span style={{ display: 'block', fontSize: 11, color: activeTab === i ? '#4b5563' : 'var(--dim)', marginTop: 3 }}>{t.sub}</span>
            {/* Progress bar */}
            <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 2, background: 'var(--border)' }}>
              <div ref={fillRefs[i]} style={{ height: '100%', background: 'linear-gradient(90deg,var(--violet),var(--pink))', width: '0%' }}/>
            </div>
          </button>
        ))}
      </div>

      {/* Panels */}
      <div style={{ maxWidth: 1100, margin: '0 auto', border: '1px solid var(--border)', borderTop: 'none', borderRadius: '0 0 14px 14px', overflow: 'hidden', background: '#050509' }}>
        {panels[activeTab]}
      </div>
    </section>
  )
}
```

- [ ] **Step 2: Handle demo bar label ref**

The `DemoBar` in Panel1 needs to accept a ref for the label. Update only Panel1's demo bar to use a plain `<span>` ref:

Replace the `<DemoBar>` call inside `Panel1` with an inline version:
```tsx
// inside Panel1, replace <DemoBar label={...}/> with:
<div style={{ background: '#0c0c1a', padding: '9px 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 5 }}>
  {[0,1,2].map(i => <div key={i} style={{ width: 7, height: 7, borderRadius: '50%', background: '#2a2a3e' }}/>)}
  <span ref={labelRef} style={{ fontSize: 10, color: '#2a2a3e', marginLeft: 8, fontFamily: 'monospace' }}>vortex · waiting…</span>
</div>
```

- [ ] **Step 3: Add HowItWorks to index.tsx**

```tsx
// landing/src/routes/index.tsx
import { createFileRoute } from '@tanstack/react-router'
import { HeroSection } from '~/components/HeroSection'
import { LogoBand } from '~/components/LogoBand'
import { HowItWorks } from '~/components/HowItWorks'

export const Route = createFileRoute('/')({
  component: HomePage,
})

function HomePage() {
  return (
    <>
      <HeroSection />
      <div className="section-divider"/>
      <LogoBand />
      <div className="section-divider"/>
      <HowItWorks />
    </>
  )
}
```

- [ ] **Step 4: Verify tabbed section works**

```bash
cd landing && pnpm dev --host
```
Navigate to http://localhost:5174, scroll to How It Works. Expected: 4 tabs render, progress bar fills on active tab, auto-advances, clicking a tab jumps to it, tab 2 (Process) animates chips.

- [ ] **Step 5: Commit**

```bash
git add landing/src/components/HowItWorks.tsx landing/src/routes/index.tsx
git commit -m "feat(landing): tabbed How It Works section with animated Process tab"
```

---

## Task 8: Stats + Mission + CTA

**Files:**
- Create: `landing/src/components/StatsSection.tsx`
- Create: `landing/src/components/MissionSection.tsx`
- Create: `landing/src/components/CTASection.tsx`
- Create: `landing/src/hooks/useCountUp.ts`
- Modify: `landing/src/routes/index.tsx`

- [ ] **Step 1: Create useCountUp.ts**

```typescript
// landing/src/hooks/useCountUp.ts
import { useEffect, useRef } from 'react'

export function useCountUp(target: number, duration = 1600) {
  const ref = useRef<HTMLElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el || !target) return
    const obs = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return
      obs.unobserve(el)
      const start = performance.now()
      const step = (now: number) => {
        const p = Math.min((now - start) / duration, 1)
        const eased = 1 - Math.pow(1 - p, 3)
        el.textContent = String(Math.round(eased * target))
        if (p < 1) requestAnimationFrame(step)
      }
      requestAnimationFrame(step)
    }, { threshold: 0.6 })
    obs.observe(el)
    return () => obs.disconnect()
  }, [target, duration])

  return ref
}
```

- [ ] **Step 2: Create StatsSection.tsx**

```tsx
// landing/src/components/StatsSection.tsx
import * as React from 'react'
import { useScrollReveal } from '~/hooks/useScrollReveal'
import { useCountUp } from '~/hooks/useCountUp'

function CountStat({ target, suffix, sym, label }: { target?: number; suffix?: string; sym?: string; label: string }) {
  const numRef = useCountUp(target ?? 0)
  return (
    <div style={{ padding: '52px 28px', textAlign: 'center', borderRight: '1px solid var(--border)', position: 'relative', flex: 1 }}>
      <div style={{ position: 'absolute', top: 0, left: '50%', transform: 'translateX(-50%)', width: '60%', height: 1, background: 'linear-gradient(90deg,transparent,rgba(167,139,250,.25),transparent)' }}/>
      <div style={{ fontSize: 48, fontWeight: 900, letterSpacing: '-.06em', lineHeight: 1, background: 'linear-gradient(135deg,var(--pink),var(--violet))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', marginBottom: 8 }}>
        {sym ? sym : <><span ref={numRef as any}>{target ? '0' : '0'}</span>{suffix}</>}
      </div>
      <div style={{ fontSize: 13, color: 'var(--muted)', fontWeight: 500, lineHeight: 1.4 }} dangerouslySetInnerHTML={{ __html: label }}/>
    </div>
  )
}

export function StatsSection() {
  const ref = useScrollReveal<HTMLDivElement>()
  return (
    <div ref={ref} className="reveal" style={{ display: 'flex', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
      <CountStat target={10} suffix="+"  label="AI models<br/>supported"/>
      <CountStat sym="∞"                 label="Knowledge base<br/>size limit"/>
      <CountStat target={100} suffix="%" label="Self-hostable &amp;<br/>open source"/>
      <CountStat sym="&lt;1s"            label="First token<br/>latency"/>
    </div>
  )
}
```

- [ ] **Step 3: Create MissionSection.tsx**

```tsx
// landing/src/components/MissionSection.tsx
import * as React from 'react'
import { useScrollReveal } from '~/hooks/useScrollReveal'

export function MissionSection() {
  const quoteRef = useScrollReveal<HTMLParagraphElement>()
  const attrRef  = useScrollReveal<HTMLDivElement>()
  const markRef  = useScrollReveal<HTMLDivElement>()

  return (
    <section style={{ padding: '110px 48px', textAlign: 'center', position: 'relative', overflow: 'hidden', borderTop: '1px solid var(--border)' }}>
      <div style={{ position: 'absolute', width: 800, height: 500, background: 'radial-gradient(ellipse,rgba(167,139,250,.05),transparent 70%)', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', pointerEvents: 'none' }}/>
      <div style={{ maxWidth: 780, margin: '0 auto', position: 'relative' }}>
        <div ref={markRef} className="reveal" style={{ display: 'flex', justifyContent: 'center', marginBottom: 32 }}>
          <svg width="48" height="48" viewBox="0 0 80 80" fill="none" style={{ filter: 'drop-shadow(0 0 18px rgba(167,139,250,.5))' }}>
            <defs>
              <linearGradient id="mg" x1="12" y1="8" x2="68" y2="72" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stopColor="#f472b6"/><stop offset="50%" stopColor="#a78bfa"/><stop offset="100%" stopColor="#60a5fa"/>
              </linearGradient>
            </defs>
            <g style={{ animation: 'msway 4s ease-in-out infinite', transformOrigin: '40px 40px' }}>
              <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="url(#mg)" strokeWidth="2.5"/>
              <line x1="40" y1="8" x2="68" y2="40" stroke="#f472b6" strokeWidth="1.5" opacity=".5"/>
              <line x1="40" y1="8" x2="40" y2="72" stroke="#a78bfa" strokeWidth="1.5" opacity=".5"/>
              <line x1="40" y1="8" x2="12" y2="40" stroke="#60a5fa" strokeWidth="1.5" opacity=".5"/>
            </g>
            <circle cx="40" cy="40" r="4.5" fill="#e0d7ff"/>
          </svg>
        </div>
        <p ref={quoteRef} className="reveal" style={{ fontSize: 'clamp(20px,2.8vw,34px)', fontWeight: 700, letterSpacing: '-.035em', lineHeight: 1.4, marginBottom: 22 }}>
          "Our mission is to make working with AI{' '}
          <span style={{ color: 'var(--violet)' }}>as natural as thinking</span>{' '}
          — so teams stop fighting their tools and start{' '}
          <span style={{ color: 'var(--pink)' }}>shipping what matters</span>."
        </p>
        <div ref={attrRef} className="reveal" style={{ fontSize: 14, color: 'var(--dim)' }}>— The Vortex team</div>
      </div>
    </section>
  )
}
```

- [ ] **Step 4: Create CTASection.tsx**

```tsx
// landing/src/components/CTASection.tsx
import * as React from 'react'
import { useScrollReveal } from '~/hooks/useScrollReveal'
import { getAppUrl } from '~/lib/app-url'

export function CTASection() {
  const titleRef   = useScrollReveal<HTMLHeadingElement>()
  const subRef     = useScrollReveal<HTMLParagraphElement>()
  const actionsRef = useScrollReveal<HTMLDivElement>()

  return (
    <section style={{ padding: '120px 48px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 22, position: 'relative', overflow: 'hidden', background: 'var(--bg2)', borderTop: '1px solid var(--border)' }}>
      <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse 80% 70% at 50% 100%,rgba(167,139,250,.06),transparent 60%)', pointerEvents: 'none' }}/>
      <h2 ref={titleRef} className="reveal" style={{ fontSize: 'clamp(30px,5vw,58px)', fontWeight: 900, letterSpacing: '-.05em', lineHeight: 1.05, maxWidth: 600, position: 'relative' }}>
        Your team deserves<br/>
        <span style={{ background: 'linear-gradient(90deg,var(--pink),var(--violet),var(--blue))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
          better AI tooling.
        </span>
      </h2>
      <p ref={subRef} className="reveal" style={{ fontSize: 17, color: 'var(--muted)', maxWidth: 440, lineHeight: 1.65, position: 'relative' }}>
        Start for free. No credit card. Deploy on your own infrastructure in minutes.
      </p>
      <div ref={actionsRef} className="reveal" style={{ display: 'flex', gap: 14, position: 'relative' }}>
        <a href={`${getAppUrl()}/register`} style={{ padding: '14px 32px', background: 'linear-gradient(135deg,var(--pink),var(--violet) 60%,var(--blue))', color: '#fff', fontSize: 15, fontWeight: 700, borderRadius: 10, textDecoration: 'none', boxShadow: '0 4px 32px rgba(167,139,250,.3)' }}>Get started free →</a>
        <a href="#" style={{ padding: '14px 28px', background: 'transparent', border: '1px solid var(--b2)', color: '#4b5563', fontSize: 15, fontWeight: 500, borderRadius: 10, textDecoration: 'none' }}>Talk to us</a>
      </div>
    </section>
  )
}
```

- [ ] **Step 5: Wire all sections into index.tsx**

```tsx
// landing/src/routes/index.tsx
import { createFileRoute } from '@tanstack/react-router'
import { HeroSection }    from '~/components/HeroSection'
import { LogoBand }       from '~/components/LogoBand'
import { HowItWorks }     from '~/components/HowItWorks'
import { StatsSection }   from '~/components/StatsSection'
import { MissionSection } from '~/components/MissionSection'
import { CTASection }     from '~/components/CTASection'

export const Route = createFileRoute('/')({
  component: HomePage,
})

function HomePage() {
  return (
    <>
      <HeroSection />
      <div className="section-divider"/>
      <LogoBand />
      <div className="section-divider"/>
      <HowItWorks />
      <StatsSection />
      <MissionSection />
      <CTASection />
    </>
  )
}
```

- [ ] **Step 6: Verify full page**

```bash
cd landing && pnpm dev --host
```
Scroll through the full page. Expected: all sections render, stats count up on scroll, mission quote reveals, CTA is visible at bottom.

- [ ] **Step 7: Commit**

```bash
git add landing/src/hooks/useCountUp.ts landing/src/components/StatsSection.tsx landing/src/components/MissionSection.tsx landing/src/components/CTASection.tsx landing/src/routes/index.tsx
git commit -m "feat(landing): stats, mission, and CTA sections"
```

---

## Task 9: Playwright E2E Tests

**Files:**
- Create: `landing/playwright.config.ts`
- Create: `landing/e2e/landing.spec.ts`
- Modify: `landing/package.json` (add test scripts)

- [ ] **Step 1: Install Playwright**

```bash
cd landing && pnpm add -D @playwright/test && pnpm exec playwright install chromium
```
Expected: Playwright installed, chromium browser downloaded.

- [ ] **Step 2: Create playwright.config.ts**

```typescript
// landing/playwright.config.ts
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  use: {
    baseURL: 'http://localhost:5174',
  },
  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:5174',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  workers: 2,
  retries: 0,
})
```

- [ ] **Step 3: Add test scripts to package.json**

Add to `scripts`:
```json
"test:e2e":    "playwright test",
"test:e2e:ui": "playwright test --ui",
"test:e2e:filter": "playwright test --grep"
```

- [ ] **Step 4: Create e2e/landing.spec.ts**

```typescript
// landing/e2e/landing.spec.ts
import { test, expect } from '@playwright/test'

test.describe('Landing page', () => {

  test('loads with Vortex title', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveTitle(/Vortex/)
  })

  test('announce bar is visible', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText(/web search.*multi-model/i)).toBeVisible()
  })

  test('nav has sign in and get started', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('link', { name: /sign in/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /get started/i }).first()).toBeVisible()
  })

  test('hero h1 contains "Ask anything"', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Ask anything')
  })

  test('hero CTA "Start for free" is visible', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('link', { name: /start for free/i })).toBeVisible()
  })

  test('logo band is present', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('Anthropic').first()).toBeVisible()
  })

  test('How It Works section has 4 tabs', async ({ page }) => {
    await page.goto('/')
    await page.locator('#hiw').scrollIntoViewIfNeeded()
    await expect(page.getByRole('button', { name: /compose/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /process/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /knowledge/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /memory/i })).toBeVisible()
  })

  test('clicking Knowledge tab shows Knowledge panel', async ({ page }) => {
    await page.goto('/')
    await page.locator('#hiw').scrollIntoViewIfNeeded()
    await page.getByRole('button', { name: /knowledge/i }).click()
    await expect(page.getByText(/Grounded answers/i)).toBeVisible()
  })

  test('clicking Memory tab shows Memory panel', async ({ page }) => {
    await page.goto('/')
    await page.locator('#hiw').scrollIntoViewIfNeeded()
    await page.getByRole('button', { name: /memory/i }).click()
    await expect(page.getByText(/Never repeat/i)).toBeVisible()
  })

  test('footer is present with product links', async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
    await expect(page.getByText('Knowledge Bases').first()).toBeVisible()
    await expect(page.getByText(/© 2026 Vortex/i)).toBeVisible()
  })

  test('hero app demo frame renders', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('vortex.app/chat/conversations/42')).toBeVisible()
    await expect(page.getByText('Q3 Risk Analysis')).toBeVisible()
  })

})
```

- [ ] **Step 5: Run E2E tests**

```bash
cd landing && pnpm test:e2e
```
Expected: all 11 tests pass. If any fail, fix the selector or component before continuing.

- [ ] **Step 6: Commit**

```bash
git add landing/playwright.config.ts landing/e2e/landing.spec.ts landing/package.json landing/pnpm-lock.yaml
git commit -m "test(landing): Playwright E2E test suite — 11 tests covering all sections"
```

---

## Task 10: Build Verification + Meta Tags

**Files:**
- Modify: `landing/src/routes/__root.tsx` (description meta tag)

- [ ] **Step 1: Run production build**

```bash
cd landing && pnpm build
```
Expected: `dist/` directory created, no TypeScript errors, no build errors.

If there are TypeScript errors, fix them — common issues:
- `ref` type mismatches: add explicit generic `useRef<HTMLDivElement>(null)`
- Missing `null` checks before accessing refs in effects: add `if (!ref.current) return`

- [ ] **Step 2: Run E2E tests one final time against dev server**

```bash
cd landing && pnpm test:e2e
```
Expected: all 11 tests pass.

- [ ] **Step 3: Final commit**

```bash
git add landing/
git commit -m "feat(landing): Vortex marketing landing page complete

Full overhaul of landing/ sub-project with dark Vortex brand:
- Tabbed How It Works with auto-advancing progress bars
- Hero animated chat demo (looping)
- Process tab chip animation with AbortController
- Scroll reveal, count-up stats, logo marquee
- Playwright E2E tests (11 tests passing)"
```

---

## Self-Review

**Spec coverage check:**
- [x] Announce bar → Task 2
- [x] Nav (Vortex dark, sticky, glassmorphism) → Task 2
- [x] Hero text + shine animation → Task 3
- [x] Hero app demo frame (static) → Task 3
- [x] Hero animation sequence (type → chips → thinking → stream) → Task 4
- [x] Logo band (marquee) → Task 5
- [x] useScrollReveal hook → Task 5
- [x] HowItWorks tabs (4 tabs, auto-advance, progress bar) → Task 7
- [x] Tab 1 Compose demo → Task 7
- [x] Tab 2 Process chip animation (AbortController) → Tasks 6 + 7
- [x] Tab 3 Knowledge demo → Task 7
- [x] Tab 4 Memory demo → Task 7
- [x] Stats count-up → Task 8
- [x] Mission section → Task 8
- [x] CTA section → Task 8
- [x] Footer → Task 2
- [x] Design tokens (CSS vars) → Task 1
- [x] All animation keyframes → Task 1
- [x] E2E tests → Task 9
- [x] Production build → Task 10

**Type consistency:**
- `HeroDemoRefs` defined in `demo-hero.ts`, used in `HeroSection.tsx` → matches
- `ChipDemoRefs` defined in `demo-chips.ts`, used in `HowItWorks.tsx` → matches
- `useScrollReveal<T>` generic used consistently across components → matches
- `useCountUp` returns `ref` used in `StatsSection` → matches

**No placeholders found.**
