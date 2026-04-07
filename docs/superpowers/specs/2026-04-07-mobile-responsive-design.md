# Mobile Responsive Design

**Date:** 2026-04-07
**Status:** Approved

## Overview

Make the AI Portal fully usable on mobile phones. The app currently has a fixed desktop sidebar layout with no mobile adaptations. This spec covers navigation, the chat composer, page-level responsive changes, touch interactions, and page transitions.

Design constraints: use the existing neutral Tailwind palette, Lucide icons, and existing component conventions throughout.

---

## Breakpoint Strategy

- **Mobile:** `< 768px` (below Tailwind `md`)
- **Desktop:** `>= 768px` (Tailwind `md` and above)

A `useIsMobile()` hook returns `true` below 768px, SSR-safe (defaults to `false` on first render to avoid hydration mismatch). It listens to `window.resize` and debounces updates.

`__root.tsx` renders `<MobileAppShell>` or the existing `<AppShell>` based on this hook. Both wrap the same `<Outlet />` — all page routes are unchanged.

---

## New Files

| File | Purpose |
|---|---|
| `hooks/useIsMobile.ts` | Breakpoint hook |
| `components/layout/MobileAppShell.tsx` | Root mobile shell |
| `components/layout/BottomTabBar.tsx` | 4 tabs + More tab |
| `components/layout/MobileHeader.tsx` | Per-route top bar |
| `components/layout/ConversationDrawer.tsx` | Slide-in conversations list |
| `components/chat/ChatComposerDockMobile.tsx` | iMessage-style composer |

---

## Navigation — Bottom Tab Bar

Replaces the sidebar entirely on mobile.

**Tabs (always rendered in this order):**
1. Home — `LayoutDashboard` icon → `/`
2. Chat — `MessageSquare` icon → `/chat/conversations`
3. Knowledge Bases — `Library` icon → `/knowledge-bases`
4. Memories — `Brain` icon → `/memories`
5. More — `MoreHorizontal` icon → opens bottom sheet

**Active state:** filled icon color `text-neutral-900 dark:text-neutral-100`, label `font-medium`. Inactive: `text-neutral-500`.

**More tab:**
- Always the 5th slot, even when only 4 routes exist today
- Tapping opens a bottom sheet (`<dialog>`) listing overflow nav items (initially: Org Settings)
- If the current route is an overflow item, More tab shows a dot badge (`bg-neutral-900 dark:bg-neutral-100`, 6px circle)
- Sheet closes on backdrop tap or any item tap

**Safe area:** `padding-bottom: env(safe-area-inset-bottom)` on the tab bar container to respect iPhone home indicator.

**Height:** 56px + safe area inset.

---

## Mobile Header

Shown at the top of the screen on mobile. Content varies by route.

**Chat route (`/chat/conversations/*`):**
- Left: `Menu` (Lucide) icon button → opens ConversationDrawer
- Center: truncated current conversation title, or "New conversation"
- Right: `SquarePen` (Lucide) icon button → navigates to `/chat/conversations` (new thread)

**All other routes:**
- Left: App title "AI Portal" (text, links to `/`)
- Right: nothing (reserved for future route-specific actions)

Height: 48px. Background `bg-white dark:bg-neutral-950`, border-bottom `border-neutral-200 dark:border-neutral-800`.

---

## Conversation Drawer

Slide-in panel triggered by the hamburger button in the mobile chat header.

**Layout:**
- Width: 85vw, max 320px
- Slides in from the left: `translateX(-100%)` → `translateX(0)`, `duration-200 ease-out`
- Backdrop: remaining right portion dims to `bg-black/30`
- Backdrop tap → close
- Swipe-left gesture on the drawer → close (touch event, threshold 60px)

**Content:** Reuses the existing `ConversationsSidebarPanel` component unchanged. No duplication.

**Header inside drawer:**
- "Conversations" label (left) + "New" button (right, `text-xs`, `SquarePen` icon)

**Close:** `X` (Lucide) button top-right, or swipe-left, or backdrop tap.

**Conversation items — swipe-to-delete:**
- Swipe left on an item reveals a red delete button (`bg-red-600`, `Trash2` icon)
- Confirm tap deletes the conversation
- Implemented with `touchstart`/`touchmove`/`touchend`, threshold 60px

---

## Chat Composer — Mobile Variant (`ChatComposerDockMobile`)

Accepts the same props as `ChatComposerDock`. Structurally different layout:

```
[ Active capability tags (if any) — dismissible ]
┌─────────────────────────────────────────┐
│  Message…                         [↑]   │  ← pill shape, send inside
└─────────────────────────────────────────┘
 [Paperclip]  [Sparkles]  [Model ▾]  [Settings2]
```

**Textarea pill:**
- `rounded-full` border, `border-neutral-200 dark:border-neutral-800`
- Auto-grows up to 6 lines (more than desktop), then scrolls
- `Enter` = newline on mobile (no keyboard submit — submit only via button)
- Send button (`ArrowUp`, Lucide) lives inside the pill on the right
  - Disabled (opacity-40) when draft is empty or composer disabled
  - `bg-neutral-900 dark:bg-neutral-100`, `rounded-full`, 32px

**Icon tray (below pill), all buttons 44px touch target:**
- `Paperclip` → attach files (same logic as desktop)
- `Sparkles` → opens capability sheet (bottom sheet listing Reflection / Research / Web stance as toggle rows)
- Model name chip → opens model picker (existing `<Select>`, positioned above via `side="top"`)
- `Settings2` → opens model tuning modal

**Active capabilities:** shown as dismissible tags (`CapabilityTag` reused) above the textarea pill when any are on.

**Keyboard avoidance:** composer uses `position: sticky; bottom: 0` within the scroll container. A `visualViewport` resize listener adjusts bottom offset when the soft keyboard opens, keeping the composer above the keyboard.

---

## Page-level Responsive Adaptations (Tailwind only, no new components)

### All modals and dialogs
On mobile (`< md`): render as a bottom sheet instead of a centered dialog.
- `fixed bottom-0 inset-x-0 rounded-t-2xl` with `max-h-[90vh] overflow-y-auto`
- Drag handle bar at the top (`w-10 h-1 bg-neutral-300 rounded-full mx-auto mb-4`)
- Affects: `CreateKnowledgeBaseDialog`, `ModelTuningModal`, `RequestAccessModal`

### `ConversationThreadPage`
- Message bubble max-width: `max-w-[85%]` (from desktop `max-w-[70%]`)
- Add `px-3` on mobile (from `px-4`)

### `HomePage`
- Padding: `p-4 md:p-6`
- Feature grid already uses `sm:grid-cols-2` ✓ — no change needed

### `MemoriesPage`
- Ensure memory cards stack single-column below `sm`
- Add `px-4 md:px-6` padding

### Knowledge Bases index
- Table view: `hidden md:block`
- Card list view: `block md:hidden` — each KB as a tappable card with name, connector count, doc count

### `KnowledgeBaseConnectorsSection`
- Connector cards stack vertically on mobile

---

## Page Transitions

Implemented via CSS classes toggled by the router's navigation events (TanStack Router `onNavigate` / route lifecycle).

**Pattern:** Each route's root element gets a `page-enter` class on mount:

```css
@keyframes page-enter {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
.page-enter {
  animation: page-enter 150ms ease-out both;
}
```

- Duration: 150ms — fast enough to feel snappy, not distracting
- Easing: `ease-out`
- Applied to: all route page root elements
- The drawer slide-in uses `transition-transform duration-200 ease-out` (existing Tailwind utility)
- Bottom sheet slides use `transition-transform duration-200 ease-out` from `translateY(100%)` → `translateY(0)`
- Tab bar itself does not animate on navigation (it's persistent chrome)

---

## Touch Interactions Summary

| Interaction | Behaviour |
|---|---|
| Swipe left on ConversationDrawer | Close drawer |
| Swipe left on conversation item | Reveal delete button |
| Tap backdrop behind drawer | Close drawer |
| Tap backdrop behind bottom sheet | Close sheet |
| Tap More tab | Open More bottom sheet |
| Tap outside model picker | Close picker |
| Pull-to-refresh on conversation list | Refresh conversations query |

---

## What Is Not In Scope

- Tablet-specific layouts (tablet gets the desktop layout at `md+`)
- Offline / PWA support
- Push notifications
- Native app (React Native)
- Swipe-between-tabs gesture (tab switching is tap-only)
