# Vortex Marketing Landing Page — Design Spec

**Date:** 2026-04-15
**Mockup:** [`docs/superpowers/vortex-landing-mockup.html`](../vortex-landing-mockup.html)

---

## Overview

A standalone marketing website for Vortex — a public-facing page that sells the product to developers and teams before they sign up. Inspired by voidzero.dev in tone: dark, minimal, motion-forward, developer-credible.

This is a **separate sub-project** from the main app. It shares the same tech stack (React + Vite + Tailwind CSS v4 + TypeScript) but lives in its own directory and deploys independently.

---

## Goals

- Convert visitors to sign-ups ("Start for free" CTA)
- Communicate what Vortex does in under 10 seconds (hero)
- Show — not tell — how the app works (animated demo, tabbed How It Works)
- Establish brand credibility (dark/purple/pink/blue gradient, PrismLogo)

---

## Tech Stack

| Concern | Choice |
|---|---|
| Framework | React 19 + Vite |
| Styling | Tailwind CSS v4 |
| Language | TypeScript |
| Animations | CSS + vanilla JS (`requestAnimationFrame`, `IntersectionObserver`) |
| Canvas | None — all animations are DOM/CSS |
| Routing | Single page (`index.html`) — no router needed |
| Deployment | Static hosting (Cloudflare Pages / Render static) |

**No Three.js, no GSAP, no WebGL.** Same approach as voidzero.dev: Canvas 2D (hero) + CSS keyframes.

---

## Project Structure

```
landing/
├── index.html
├── vite.config.ts
├── package.json
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── styles/
│   │   └── global.css          # Tailwind v4 + CSS custom properties
│   ├── components/
│   │   ├── Nav.tsx
│   │   ├── Hero.tsx             # Hero section + animated app demo
│   │   ├── LogoBand.tsx         # CSS marquee logo strip
│   │   ├── HowItWorks.tsx       # Tabbed section (main feature)
│   │   ├── Stats.tsx            # Count-up numbers
│   │   ├── Mission.tsx
│   │   ├── CTA.tsx
│   │   └── Footer.tsx
│   ├── hooks/
│   │   ├── useScrollReveal.ts   # IntersectionObserver reveal
│   │   └── useCountUp.ts        # Number animation on scroll
│   └── lib/
│       ├── demo-hero.ts         # Hero chat animation sequence
│       └── demo-chips.ts        # Step 2 chip animation sequence
```

---

## Design Tokens

From the Vortex brand (see `docs/superpowers/plans/2026-04-11-vortex-brand.md`):

```css
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
```

---

## Sections

### 1. Announce Bar
Thin top bar. Gradient background. Changelog/release note. Pink accent label.

### 2. Nav
Sticky. Glassmorphism (`backdrop-filter: blur`). PrismLogo + VortexWordmark. Links: Features / Docs / Blog. Right: Sign in (ghost) + Get started (gradient CTA).

### 3. Hero

**Text block:**
- Eyebrow: `AI Portal · Built for Teams`
- H1 three-liner: "Ask anything." / "Know everything." (gradient shine sweep animation) / "Ship faster." (dim)
- Sub copy
- Two CTAs: primary gradient button + ghost button

**App demo frame:**
A faithful replica of the real app shell — browser chrome, sidebar with conversations + KBs, chat header, scrollable thread, ComposerDock with capability tags (Reflection/Research), KB chip, textarea, send button.

**Hero animation sequence** (loops, starts on page load):
1. Types user message into composer (28ms/char, random jitter)
2. Send button flash → composer clears
3. User bubble appears
4. Memory chip: loading (spinning PrismLogo) → resolved (green ✓)
5. KB chip: loading → resolved
6. Thinking dots (3-dot bounce)
7. AI response streams character-by-character
8. KB source indicator appears below
9. 6s pause → reset and loop

### 4. Logo Band
CSS marquee (`translateX` infinite). 8 company names × 2 (seamless loop). Fade mask on edges. Pauses on hover.

### 5. How It Works ← **key section**

Tabbed interface. 4 tabs auto-advance with a progress bar. Starts when section enters viewport (IntersectionObserver). Click any tab to jump.

**Tab bar:**
- 4 tabs in a grid row, each with: step number (monospace), label, one-line description, progress bar (fills left→right during countdown)
- Active tab: lighter background, violet step number
- Progress bar: `linear-gradient(violet → pink)`, `transition: width Ns linear`

**Durations:** Tab 1=5s, Tab 2=11s (needs animation time), Tab 3=5s, Tab 4=5s. Loops continuously.

**Tab 1 — Compose:**
- Text: model picker, Research/Reflection toggles, KB attach
- Demo: ComposerDock close-up with capability tags, KB chip, typed query, send button

**Tab 2 — Process:**
- Text: memory, KB search, web search, live tool visibility
- Demo: animated chat — user message already shown, then chips animate (memory loading → ✓, KB loading → ✓), thinking dots, AI response streams in. Replays every time the tab activates. Aborts cleanly via `AbortController` if tab is switched mid-animation.

**Tab 3 — Knowledge:**
- Text: KB attach, semantic search, cited answers
- Demo: expanded KB chip showing sources panel + "used knowledge bases" block

**Tab 4 — Memory:**
- Text: auto-learned context, editable, injected per thread
- Demo: memory chip (resolved) + 3 memory rows styled like the real MemoriesPage (preference/context/tools, left-border color coding)

### 6. Stats
4-column grid. Count-up animation on scroll (easeOutCubic, 1.6s). Values: `10+` models, `∞` KB size, `100%` self-hostable, `<1s` first token.

### 7. Mission
Centered quote. Animated PrismLogo (slow rock). Gradient text highlights.

### 8. CTA
Full-width. Radial glow from bottom. H2 + sub + two buttons.

### 9. Footer
4-column grid: brand + Product / Developers / Company link columns.

---

## Animations

### Scroll Reveal
All non-hero sections reveal on scroll via `IntersectionObserver` with `{ once: true }` (one-shot). Three variants:
- `.reveal` — fade up from `translateY(28px)`
- `.reveal-left` — fade in from `translateX(-32px)`
- `.reveal-right` — fade in from `translateX(32px)`
- Stagger delays via `.d1`–`.d4` utility classes

### Shine Text
Hero H1 gradient line uses `background-clip: text` + `@keyframes shineSweep` moving `background-position` from `100% 0` to `15% 0` on a 400%-wide gradient. Runs once on load.

### Chip States
Matches real `ThreadItemChip` component exactly:
- Memory: `border-color: rgba(59,130,246,.35)`, `background: rgba(23,37,84,.4)`, `color: #93c5fd`
- KB search: `border-color: rgba(126,34,206,.4)`, `background: rgba(59,7,100,.3)`, `color: #c4b5fd`
- Loading: spinning PrismLogo SVG (`animation: prismSpin 1s linear infinite`)
- Done: green checkmark SVG (`color: #22c55e`)

### Thinking Dots
3-dot bounce (`translateY(-5px)`) with staggered delays (0 / 180ms / 360ms). Appears between last chip resolving and first token.

---

## Component Reference: Real App Replicas

The landing page demo frames faithfully replicate these real components so visitors recognize the actual product:

| Demo element | Real component |
|---|---|
| Composer dock | `ChatComposerDock.tsx` |
| Tool chips | `ThreadItemChip.tsx` |
| Sidebar + thread | `ConversationThreadPage.tsx` |
| Memory rows | `MemoriesPage.tsx` |
| PrismLogo spinner | `PrismLogo` with `state="loading"` |

---

## Visual Reference

The approved mockup is the source of truth for all visual decisions:

**File:** `docs/superpowers/vortex-landing-mockup.html`

Open in a browser to see the full interactive demo with all animations. Every layout, spacing, color, and animation timing in this spec is derived from that file.
