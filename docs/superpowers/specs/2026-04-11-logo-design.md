# Logo Design Spec — AI Portal

**Date:** 2026-04-11  
**Status:** In Progress (name TBD)

---

## Decisions Made

### Mark: Prism (Diamond)
A diamond/rhombus shape (rotated square, 4 equal sides) with a central core dot and three colored rays emanating from the top vertex. Represents multiple AI providers unified through one interface — light entering a prism and refracting into a spectrum.

SVG geometry (80×80 viewBox):
```
points="40,8 68,40 40,72 12,40"   ← diamond outline
top vertex:  (40, 8)
right vertex: (68, 40)
bottom vertex: (40, 72)
left vertex:  (12, 40)
core dot: cx=40 cy=40 r=4–7 (varies by state)
rays: top-vertex → right, bottom, left vertices
```

### Color: Violet Spectrum
Pink → Purple → Blue gradient.
```
Ray 1 (→ right):   #f472b6  (pink)
Ray 2 (→ bottom):  #a78bfa  (purple)
Ray 3 (→ left):    #60a5fa  (blue)
Outline gradient:  #f472b6 → #a78bfa → #60a5fa
Core dot:          #e0d7ff  (near-white lavender)
```

### Motion: Pendulum
The prism swings left/right like a pendulum (`rotate(-18deg)` ↔ `rotate(18deg)`), with 2 ghost trail copies fading behind it (opacity 0.2 and 0.08). Rays sweep in and out during the swing. This is the base motion used in active states; speed and ray intensity vary by state.

---

## State System

### 1. Idle
**When:** App open, no active request.  
**Animation:** Slow gentle sway — `rotate(-5deg) ↔ rotate(5deg)`, 4s ease-in-out.  
**Rays:** Static, opacity 0.35 (dim, present but quiet).  
**Core:** Subtle pulse r=4→5.5.  
**Colors:** Full violet spectrum.

```css
@keyframes idleSway {
  0%,100% { transform: rotate(-5deg); }
  50%     { transform: rotate(5deg); }
}
/* duration: 4s ease-in-out infinite */
```

---

### 2. Loading (Awaiting First Token)
**When:** Message sent, waiting for API first response byte.  
**Animation:** Fast continuous rotation (full 360°), 1.2s linear. Two ghost trail polygons (opacity 0.25, 0.1) offset behind.  
**Rays:** Stroke-dasharray sweep, redrawing every revolution.  
**Colors:** Full violet spectrum.

```css
@keyframes loadSpin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
/* duration: 1.2s linear infinite */
/* trails: same keyframe, delay -0.1s and -0.2s */
```

---

### 3. Streaming
**When:** Tokens actively arriving from the model.  
**Animation:** Pendulum swing `rotate(-18deg) ↔ rotate(18deg)`, 1.8s ease-in-out. Two ghost trails. Rays sweep in/out synced to swing.  
**Core:** Pulses r=4→7 with `drop-shadow(0 0 6px #a78bfa)`.  
**Colors:** Full violet spectrum.

```css
@keyframes pendulum {
  0%   { transform: rotate(-18deg); }
  50%  { transform: rotate(18deg); }
  100% { transform: rotate(-18deg); }
}
/* duration: 1.8s ease-in-out infinite */
```

---

### 4. Thinking (Reasoning Mode)
**When:** Model is in extended thinking / chain-of-thought (Claude Sonnet 4.6, Gemini 3.1 Pro).  
**Animation:** Slow pendulum `rotate(-18deg) ↔ rotate(18deg)`, 3.5s ease-in-out. Two ghost trails.  
**Color shift:** Entire palette shifts to **amber/gold** — visually distinct from streaming.  
```
Ray 1: #fbbf24  (amber)
Ray 2: #f59e0b  (dark amber)
Ray 3: #fde68a  (light gold)
Core:  #fde68a  with drop-shadow(0 0 10px #fbbf24)
```

```css
/* Same pendulum keyframe, duration: 3.5s ease-in-out infinite */
/* Core: drop-shadow(0 0 10px #fbbf24) at peak */
```

---

### 5. Error
**When:** API error, network failure, model quota exceeded.  
**Animation:** Shake — rapid horizontal translate + slight rotate, 0.5s ease-in-out infinite.  
**Color shift:** Full palette shifts to **red**.
```
Outline: #ef4444
Rays:    #f87171 / #ef4444 / #fca5a5
Core:    #fca5a5
```

```css
@keyframes shake {
  0%,100% { transform: translateX(0) rotate(0deg); }
  15%     { transform: translateX(-4px) rotate(-3deg); }
  35%     { transform: translateX(4px)  rotate(3deg); }
  55%     { transform: translateX(-3px) rotate(-2deg); }
  75%     { transform: translateX(3px)  rotate(2deg); }
  90%     { transform: translateX(-1px) rotate(-1deg); }
}
/* duration: 0.5s ease-in-out infinite */
```

---

### 6. Mono White (Dark backgrounds)
**When:** Dark nav bars, headers, favicon on dark bg, sidebar icon.  
**Animation:** Same slow sway as Idle.  
**Colors:** `stroke="#e0d7ff"` outline, white rays at opacity 0.3–0.5, white core.  
No gradient — single color only.

---

### 7. Mono Dark (Light backgrounds)
**When:** Light mode UI, print, email, light nav bar.  
**Animation:** Same slow sway as Idle.  
**Colors:** `stroke="#1a1a2e"` outline, dark rays at opacity 0.3–0.5, dark core.  
No gradient — single color only.

---

## Size Variants

| Size | Use case |
|------|----------|
| 16px | Favicon, browser tab |
| 24px | Nav icon, sidebar |
| 40px | Button / inline |
| 64px | Loading indicator in chat |
| 96px | Splash screen, onboarding |

At 16px: increase stroke-width to 3, increase core r to 7 for legibility.  
At 24px+: standard stroke-width 2, core r 5.

---

## State Transitions (planned)

```
idle ──[send]──→ loading ──[first token]──→ streaming ──[done]──→ idle
                                         ↘ thinking (if thinking_delta arrives first)
                                         ↗
         [error at any point] ──→ error ──[dismiss/retry]──→ idle
```

---

## Files to Create (implementation)

- `frontend/src/components/brand/PrismLogo.tsx` — React component, accepts `state` prop
- `frontend/src/components/brand/prism-logo.css` — all keyframe animations
- States prop: `'idle' | 'loading' | 'streaming' | 'thinking' | 'error' | 'mono-white' | 'mono-dark'`
- Size prop: `number` (default 64)

---

## Name (TBD)

Naming brainstorm pending. Candidates to explore:
- Something referencing light/spectrum/refraction
- Something referencing the multi-provider nature
- Developer-focused, short, memorable
