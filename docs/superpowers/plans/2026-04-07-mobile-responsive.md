# Mobile Responsive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the AI Portal fully usable on mobile phones with a bottom tab bar, conversation drawer, iMessage-style composer, and responsive page layouts.

**Architecture:** A `useIsMobile()` hook (< 768px threshold) gates rendering of a new `MobileAppShell` vs the existing `AppShell` in `__root.tsx`. The mobile shell owns the bottom tab bar, top header bar, and conversation drawer. Page components adapt with Tailwind responsive classes only — no new page files. `ChatComposerDockMobile` is a structurally distinct mobile composer that accepts the same props as `ChatComposerDock`.

**Tech Stack:** React, TanStack Router, Tailwind CSS v4, Lucide React, `@tanstack/react-query`

---

## File Map

**New files:**
- `frontend/src/hooks/useIsMobile.ts`
- `frontend/src/components/layout/MobileAppShell.tsx`
- `frontend/src/components/layout/BottomTabBar.tsx`
- `frontend/src/components/layout/MobileHeader.tsx`
- `frontend/src/components/layout/ConversationDrawer.tsx`
- `frontend/src/components/chat/ChatComposerDockMobile.tsx`

**Modified files:**
- `frontend/src/styles/app.css` — page-enter animation, safe-area utility
- `frontend/src/routes/__root.tsx` — conditional shell rendering
- `frontend/src/components/chat/ConversationsRouteLayout.tsx` — hide sidebar panel on mobile
- `frontend/src/components/chat/ConversationThreadPage.tsx` — use mobile composer on mobile
- `frontend/src/routes/knowledge-bases/index.tsx` — mobile card list view
- `frontend/src/components/memories/MemoriesPage.tsx` — responsive padding
- `frontend/src/components/home/HomePage.tsx` — responsive padding
- `frontend/src/components/knowledge-bases/CreateKnowledgeBaseDialog.tsx` — bottom sheet on mobile
- `frontend/src/components/chat/ModelTuningModal.tsx` — bottom sheet on mobile

---

## Task 1: `useIsMobile` hook

**Files:**
- Create: `frontend/src/hooks/useIsMobile.ts`

- [ ] **Step 1: Create the hook**

```typescript
// frontend/src/hooks/useIsMobile.ts
import * as React from 'react'

const MOBILE_BREAKPOINT = 768

export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = React.useState(false)

  React.useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < MOBILE_BREAKPOINT)
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  return isMobile
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useIsMobile.ts
git commit -m "feat(mobile): add useIsMobile hook"
```

---

## Task 2: CSS — page-enter animation and safe-area utility

**Files:**
- Modify: `frontend/src/styles/app.css`

- [ ] **Step 1: Add animation and safe-area utility to `app.css`**

Add after the existing `@layer utilities` block:

```css
@layer utilities {
  .page-enter {
    animation: aip-page-enter 150ms ease-out both;
  }

  @keyframes aip-page-enter {
    from {
      opacity: 0;
      transform: translateY(6px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .pb-safe {
    padding-bottom: env(safe-area-inset-bottom);
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/styles/app.css
git commit -m "feat(mobile): add page-enter animation and pb-safe utility"
```

---

## Task 3: `BottomTabBar` component

**Files:**
- Create: `frontend/src/components/layout/BottomTabBar.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/layout/BottomTabBar.tsx
import { Link, useLocation } from '@tanstack/react-router'
import {
  Brain,
  LayoutDashboard,
  Library,
  MessageSquare,
  MoreHorizontal,
  Settings,
} from 'lucide-react'
import * as React from 'react'

const TABS = [
  { to: '/', icon: LayoutDashboard, label: 'Home', exact: true },
  { to: '/chat/conversations', icon: MessageSquare, label: 'Chat', exact: false },
  { to: '/knowledge-bases', icon: Library, label: 'KBs', exact: false },
  { to: '/memories', icon: Brain, label: 'Memories', exact: false },
] as const

const OVERFLOW_ITEMS = [
  { to: '/org/settings', icon: Settings, label: 'Org Settings' },
] as const

export function BottomTabBar() {
  const location = useLocation()
  const [moreOpen, setMoreOpen] = React.useState(false)

  const isOverflowActive = OVERFLOW_ITEMS.some((item) =>
    location.pathname.startsWith(item.to),
  )

  return (
    <>
      {/* More sheet backdrop */}
      {moreOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/30"
          onClick={() => setMoreOpen(false)}
          aria-hidden
        />
      )}

      {/* More sheet */}
      {moreOpen && (
        <div className="fixed bottom-0 inset-x-0 z-50 rounded-t-2xl border-t border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-950 transition-transform duration-200 ease-out">
          <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-neutral-300 dark:bg-neutral-700" />
          <p className="px-4 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wide text-neutral-400">
            More
          </p>
          {OVERFLOW_ITEMS.map(({ to, icon: Icon, label }) => (
            <Link
              key={to}
              to={to}
              onClick={() => setMoreOpen(false)}
              className="flex items-center gap-3 px-4 py-3 text-sm text-neutral-700 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              <Icon className="size-5 shrink-0 text-neutral-500 dark:text-neutral-400" aria-hidden />
              {label}
            </Link>
          ))}
          <div className="pb-safe" />
        </div>
      )}

      {/* Tab bar */}
      <nav
        className="flex shrink-0 items-stretch border-t border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-950"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
        aria-label="Main navigation"
      >
        {TABS.map(({ to, icon: Icon, label, exact }) => {
          const active = exact
            ? location.pathname === to
            : location.pathname.startsWith(to)
          return (
            <Link
              key={to}
              to={to}
              className="flex flex-1 flex-col items-center justify-center gap-0.5 py-2 text-neutral-500 dark:text-neutral-400"
              activeProps={{}}
            >
              <Icon
                className={`size-5 shrink-0 ${active ? 'text-neutral-900 dark:text-neutral-100' : ''}`}
                aria-hidden
              />
              <span
                className={`text-[10px] ${active ? 'font-semibold text-neutral-900 dark:text-neutral-100' : ''}`}
              >
                {label}
              </span>
            </Link>
          )
        })}

        {/* More tab */}
        <button
          type="button"
          onClick={() => setMoreOpen((o) => !o)}
          className="flex flex-1 flex-col items-center justify-center gap-0.5 py-2 text-neutral-500 dark:text-neutral-400 relative"
          aria-label="More navigation options"
        >
          {isOverflowActive && (
            <span className="absolute top-2 right-[calc(50%-14px)] size-1.5 rounded-full bg-neutral-900 dark:bg-neutral-100" />
          )}
          <MoreHorizontal
            className={`size-5 shrink-0 ${isOverflowActive ? 'text-neutral-900 dark:text-neutral-100' : ''}`}
            aria-hidden
          />
          <span className={`text-[10px] ${isOverflowActive ? 'font-semibold text-neutral-900 dark:text-neutral-100' : ''}`}>
            More
          </span>
        </button>
      </nav>
    </>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/layout/BottomTabBar.tsx
git commit -m "feat(mobile): add BottomTabBar with More sheet"
```

---

## Task 4: `MobileHeader` component

**Files:**
- Create: `frontend/src/components/layout/MobileHeader.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/layout/MobileHeader.tsx
import { Link, useLocation } from '@tanstack/react-router'
import { Menu, SquarePen } from 'lucide-react'
import * as React from 'react'

type MobileHeaderProps = {
  conversationTitle?: string
  onOpenDrawer?: () => void
  onNewConversation?: () => void
}

export function MobileHeader({
  conversationTitle,
  onOpenDrawer,
  onNewConversation,
}: MobileHeaderProps) {
  const location = useLocation()
  const isChatRoute = location.pathname.startsWith('/chat/conversations')

  if (isChatRoute) {
    return (
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-neutral-200 bg-white px-3 dark:border-neutral-800 dark:bg-neutral-950">
        <button
          type="button"
          onClick={onOpenDrawer}
          className="rounded-md p-2 text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
          aria-label="Open conversations"
        >
          <Menu className="size-5" aria-hidden />
        </button>
        <span className="flex-1 truncate text-sm font-semibold text-neutral-900 dark:text-neutral-100">
          {conversationTitle ?? 'New conversation'}
        </span>
        <button
          type="button"
          onClick={onNewConversation}
          className="rounded-md p-2 text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
          aria-label="New conversation"
        >
          <SquarePen className="size-5" aria-hidden />
        </button>
      </header>
    )
  }

  return (
    <header className="flex h-12 shrink-0 items-center border-b border-neutral-200 bg-white px-4 dark:border-neutral-800 dark:bg-neutral-950">
      <Link
        to="/"
        className="text-base font-semibold tracking-tight text-neutral-900 dark:text-neutral-100"
      >
        AI Portal
      </Link>
    </header>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/layout/MobileHeader.tsx
git commit -m "feat(mobile): add MobileHeader component"
```

---

## Task 5: `ConversationDrawer` component

**Files:**
- Create: `frontend/src/components/layout/ConversationDrawer.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/layout/ConversationDrawer.tsx
import { SquarePen, X } from 'lucide-react'
import * as React from 'react'

import { ConversationsSidebarPanel } from '~/components/chat/ConversationsSidebarPanel'
import type { Conversation } from '~/lib/chat-types'

type ConversationDrawerProps = {
  open: boolean
  onClose: () => void
  conversations: Conversation[] | undefined
  conversationsPending: boolean
  conversationsError: Error | null
  onNewConversation: () => void
}

export function ConversationDrawer({
  open,
  onClose,
  conversations,
  conversationsPending,
  conversationsError,
  onNewConversation,
}: ConversationDrawerProps) {
  const drawerRef = React.useRef<HTMLDivElement>(null)
  const touchStartX = React.useRef<number | null>(null)

  // Swipe-left to close
  React.useEffect(() => {
    const el = drawerRef.current
    if (!el) return
    const onTouchStart = (e: TouchEvent) => {
      touchStartX.current = e.touches[0].clientX
    }
    const onTouchEnd = (e: TouchEvent) => {
      if (touchStartX.current == null) return
      const dx = touchStartX.current - e.changedTouches[0].clientX
      if (dx > 60) onClose()
      touchStartX.current = null
    }
    el.addEventListener('touchstart', onTouchStart, { passive: true })
    el.addEventListener('touchend', onTouchEnd, { passive: true })
    return () => {
      el.removeEventListener('touchstart', onTouchStart)
      el.removeEventListener('touchend', onTouchEnd)
    }
  }, [onClose])

  // Close on Escape
  React.useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <>
      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-40 bg-black/30 transition-opacity duration-200 ${open ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
        onClick={onClose}
        aria-hidden
      />

      {/* Drawer */}
      <div
        ref={drawerRef}
        className={`fixed inset-y-0 left-0 z-50 flex w-[85vw] max-w-xs flex-col bg-white shadow-xl transition-transform duration-200 ease-out dark:bg-neutral-950 ${open ? 'translate-x-0' : '-translate-x-full'}`}
        aria-label="Conversations"
        role="dialog"
        aria-modal="true"
      >
        {/* Drawer header */}
        <div className="flex h-12 shrink-0 items-center justify-between border-b border-neutral-200 px-3 dark:border-neutral-800">
          <span className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
            Conversations
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => { onNewConversation(); onClose() }}
              className="rounded-md p-2 text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
              aria-label="New conversation"
            >
              <SquarePen className="size-4" aria-hidden />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-2 text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
              aria-label="Close conversations"
            >
              <X className="size-4" aria-hidden />
            </button>
          </div>
        </div>

        {/* Panel content */}
        <div className="min-h-0 flex-1 overflow-hidden">
          <ConversationsSidebarPanel
            conversations={conversations}
            conversationsPending={conversationsPending}
            conversationsError={conversationsError}
            onNewConversation={() => { onNewConversation(); onClose() }}
          />
        </div>
      </div>
    </>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/layout/ConversationDrawer.tsx
git commit -m "feat(mobile): add ConversationDrawer with swipe-to-close"
```

---

## Task 6: `MobileAppShell` + wire into `__root.tsx`

**Files:**
- Create: `frontend/src/components/layout/MobileAppShell.tsx`
- Modify: `frontend/src/routes/__root.tsx`

- [ ] **Step 1: Create `MobileAppShell`**

```tsx
// frontend/src/components/layout/MobileAppShell.tsx
import { useNavigate, useLocation } from '@tanstack/react-router'
import * as React from 'react'

import { BottomTabBar } from '~/components/layout/BottomTabBar'
import { MobileHeader } from '~/components/layout/MobileHeader'
import { ConversationDrawer } from '~/components/layout/ConversationDrawer'
import { useConversationsListQuery } from '~/hooks/useConversationsListQuery'
import { useConversationQuery } from '~/hooks/useConversationQuery'

function useCurrentConversationTitle(): string | undefined {
  const location = useLocation()
  // Extract id from /chat/conversations/:id
  const match = location.pathname.match(/\/chat\/conversations\/(\d+)/)
  const id = match ? Number(match[1]) : null
  const query = useConversationQuery(id)
  return query.data?.title ?? undefined
}

export function MobileAppShell({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate()
  const [drawerOpen, setDrawerOpen] = React.useState(false)
  const convsQ = useConversationsListQuery()
  const conversationTitle = useCurrentConversationTitle()

  const handleNewConversation = () => {
    void navigate({ to: '/chat/conversations' })
  }

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-white dark:bg-neutral-950">
      <MobileHeader
        conversationTitle={conversationTitle}
        onOpenDrawer={() => setDrawerOpen(true)}
        onNewConversation={handleNewConversation}
      />

      <ConversationDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        conversations={convsQ.data}
        conversationsPending={convsQ.isPending}
        conversationsError={convsQ.error as Error | null}
        onNewConversation={handleNewConversation}
      />

      <div className="min-h-0 flex-1 overflow-hidden">
        {children}
      </div>

      <BottomTabBar />
    </div>
  )
}
```

- [ ] **Step 2: Check what `useConversationQuery` expects**

Read `frontend/src/hooks/useConversationQuery.ts` to confirm the function signature accepts `number | null`. If it only accepts `number`, wrap the call:

```typescript
// If useConversationQuery(id) doesn't accept null, guard like this in MobileAppShell:
const query = id != null ? useConversationQuery(id) : { data: undefined }
```

Note: React hooks cannot be called conditionally. If `useConversationQuery` doesn't handle `null`, create a small wrapper in `useCurrentConversationTitle` that calls the hook with a sentinel value and returns `undefined` for `null` ids.

- [ ] **Step 3: Wire into `__root.tsx`**

Modify `RootComponent` in `frontend/src/routes/__root.tsx`:

```tsx
import { AppShell } from '~/components/layout/AppShell'
import { MobileAppShell } from '~/components/layout/MobileAppShell'
import { useIsMobile } from '~/hooks/useIsMobile'

function RootComponent() {
  useAuthRedirect()
  useSetupRedirect()
  const isMobile = useIsMobile()

  const Shell = isMobile ? MobileAppShell : AppShell

  const shell = (
    <Shell>
      <Outlet />
    </Shell>
  )

  return (
    <RootDocument>
      {getAuthMode() === 'entra' ? <EntraRoot>{shell}</EntraRoot> : shell}
    </RootDocument>
  )
}
```

- [ ] **Step 4: Start the dev server and verify the tab bar appears on mobile viewport**

```bash
cd frontend && pnpm dev --host
```

Open browser, set viewport to 375px wide (Chrome DevTools). Verify:
- Bottom tab bar is visible with Home, Chat, KBs, Memories, More
- Desktop sidebar is gone at mobile width
- Desktop sidebar reappears at 768px+

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/MobileAppShell.tsx frontend/src/routes/__root.tsx
git commit -m "feat(mobile): add MobileAppShell and wire into root"
```

---

## Task 7: Hide sidebar panel in `ConversationsRouteLayout` on mobile

**Files:**
- Modify: `frontend/src/components/chat/ConversationsRouteLayout.tsx`

- [ ] **Step 1: Hide `ConversationsSidebarPanel` on mobile**

The `ConversationDrawer` already handles the conversations list on mobile. The sidebar panel should be hidden on mobile so it doesn't take space:

```tsx
// In ConversationsRouteLayout, change the ConversationsSidebarPanel wrapper to:
<div className="hidden md:flex md:min-h-0 md:flex-col">
  <ConversationsSidebarPanel
    conversations={convsQ.data}
    conversationsPending={convsQ.isPending}
    conversationsError={convsQ.error as Error | null}
    onNewConversation={() => {
      void navigate({ to: '/chat/conversations' })
    }}
  />
</div>
```

Also remove the outer `md:flex-row` since on mobile the layout is now just `flex-col` with full width:

```tsx
<div className="flex min-h-0 flex-1 flex-col overflow-hidden">
  <div className="hidden md:flex md:min-h-0 md:flex-col md:shrink-0">
    <ConversationsSidebarPanel ... />
  </div>
  <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden p-2 md:p-4">
    <Outlet />
  </div>
</div>
```

- [ ] **Step 2: Verify chat opens full-width on mobile**

At 375px viewport: chat thread should take the full width, no sidebar visible. At 768px+: sidebar panel reappears on the left.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/chat/ConversationsRouteLayout.tsx
git commit -m "feat(mobile): hide sidebar panel on mobile (drawer handles it)"
```

---

## Task 8: `ChatComposerDockMobile` — iMessage-style composer

**Files:**
- Create: `frontend/src/components/chat/ChatComposerDockMobile.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/chat/ChatComposerDockMobile.tsx
import { ArrowUp, Paperclip, Settings2, Sparkles, Square, X } from 'lucide-react'
import * as React from 'react'

import {
  ModelTuningModal,
  type SessionModelTuning,
  defaultTuningFromCatalog,
} from '~/components/chat/ModelTuningModal'
import { RequestAccessModal } from '~/components/chat/RequestAccessModal'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select'
import type { CapabilityToggles, CatalogModelEntry } from '~/lib/chat-types'
import {
  catalogModelByStoredModel,
  portalDefaultCatalogModel,
} from '~/hooks/useCatalogModelsQuery'
import type { CapabilityKey } from '~/components/chat/ChatComposerDock'
import { resolveSelectedCatalogModel } from '~/components/chat/ChatComposerDock'

const CATALOG_SELECT_PREFIX = 'catalog:' as const
const COMPOSER_TEXTAREA_MAX_LINES = 6

const CAPABILITY_MENU: { key: CapabilityKey; label: string }[] = [
  { key: 'reflection', label: 'Reflection' },
  { key: 'research', label: 'Research' },
  { key: 'web', label: 'Web stance' },
]

function CapabilityTag({
  label,
  onRemove,
  disabled,
}: {
  label: string
  onRemove: () => void
  disabled?: boolean
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-neutral-200 bg-neutral-100 px-2 py-0.5 text-xs font-medium text-neutral-800 dark:border-neutral-600 dark:bg-neutral-800 dark:text-neutral-200">
      {label}
      <button
        type="button"
        className="rounded-full p-0.5 text-neutral-500 hover:bg-neutral-200 hover:text-neutral-800 dark:hover:bg-neutral-700 dark:hover:text-neutral-100"
        aria-label={`Remove ${label}`}
        disabled={disabled}
        onClick={onRemove}
      >
        <X className="h-3 w-3" strokeWidth={2.5} />
      </button>
    </span>
  )
}

type ChatComposerDockMobileProps = {
  models: CatalogModelEntry[] | undefined
  modelsPending: boolean
  modelsError: Error | null
  chatModel: string
  onSelectChatModel: (modelId: string) => void
  onCommitChatModel?: (modelId: string) => void
  modelSelectDisabled?: boolean
  capabilities: CapabilityToggles
  onToggleCapability: (key: CapabilityKey) => void
  capabilityDisabled?: boolean
  composeDraft: string
  setComposeDraft: (v: string) => void
  onSubmit: () => void
  streaming: boolean
  onStop: () => void
  inputThemed: string
  composerDisabled?: boolean
  kbSlot?: React.ReactNode
  selectedCatalogModel: CatalogModelEntry | null
  tuning: SessionModelTuning
  onTuningChange: (t: SessionModelTuning) => void
  pendingServerAttachments?: { id: number; name: string }[]
  pendingLocalFileNames?: string[]
  onRemoveServerAttachment?: (id: number) => void
  onRemoveLocalFile?: (index: number) => void
  onLocalFilesChosen?: (files: File[]) => void
  attachDisabled?: boolean
}

export function ChatComposerDockMobile({
  models,
  modelsPending,
  modelsError,
  chatModel,
  onSelectChatModel,
  onCommitChatModel,
  modelSelectDisabled,
  capabilities,
  onToggleCapability,
  capabilityDisabled,
  composeDraft,
  setComposeDraft,
  onSubmit,
  streaming,
  onStop,
  inputThemed,
  composerDisabled,
  kbSlot,
  selectedCatalogModel,
  tuning,
  onTuningChange,
  pendingServerAttachments,
  pendingLocalFileNames,
  onRemoveServerAttachment,
  onRemoveLocalFile,
  onLocalFilesChosen,
  attachDisabled,
}: ChatComposerDockMobileProps) {
  const [tuningOpen, setTuningOpen] = React.useState(false)
  const [capsOpen, setCapsOpen] = React.useState(false)
  const [requestAccessModel, setRequestAccessModel] = React.useState<CatalogModelEntry | null>(null)
  const [modelSelectOpen, setModelSelectOpen] = React.useState(false)
  const composeTextareaRef = React.useRef<HTMLTextAreaElement>(null)
  const attachInputRef = React.useRef<HTMLInputElement>(null)

  const sorted = React.useMemo(
    () =>
      models == null
        ? []
        : [...models].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id),
    [models],
  )

  const storedCatalogRow =
    chatModel === '' ? null : catalogModelByStoredModel(models, chatModel)
  const defaultCatalogRow = React.useMemo(() => portalDefaultCatalogModel(models), [models])
  const selectValue =
    chatModel === ''
      ? defaultCatalogRow != null
        ? `${CATALOG_SELECT_PREFIX}${defaultCatalogRow.slug}`
        : ''
      : storedCatalogRow != null
        ? `${CATALOG_SELECT_PREFIX}${storedCatalogRow.slug}`
        : chatModel
  const modelLabel =
    chatModel === ''
      ? (defaultCatalogRow?.display_name ?? 'Model')
      : (storedCatalogRow?.display_name ?? chatModel)

  const maxInputChars = React.useMemo(() => {
    const cap = selectedCatalogModel?.model_settings.limits?.max_input_chars
    if (typeof cap === 'number' && cap >= 1024) return cap
    return 500_000
  }, [selectedCatalogModel])

  React.useEffect(() => {
    if (composeDraft.length <= maxInputChars) return
    setComposeDraft(composeDraft.slice(0, maxInputChars))
  }, [maxInputChars, composeDraft, setComposeDraft])

  React.useLayoutEffect(() => {
    const el = composeTextareaRef.current
    if (!el) return
    el.style.height = 'auto'
    const styles = getComputedStyle(el)
    const lh = parseFloat(styles.lineHeight)
    const lineHeight = Number.isFinite(lh) && lh > 0 ? lh : 20
    const padY =
      (parseFloat(styles.paddingTop) || 0) + (parseFloat(styles.paddingBottom) || 0)
    const borderY =
      (parseFloat(styles.borderTopWidth) || 0) +
      (parseFloat(styles.borderBottomWidth) || 0)
    const maxPx = lineHeight * COMPOSER_TEXTAREA_MAX_LINES + padY + borderY
    const contentH = el.scrollHeight
    el.style.height = `${Math.min(contentH, maxPx)}px`
    el.style.overflowY = contentH > maxPx ? 'auto' : 'hidden'
  }, [composeDraft])

  const handleModelSelectChange = (v: string) => {
    const id = v.startsWith(CATALOG_SELECT_PREFIX) ? v.slice(CATALOG_SELECT_PREFIX.length) : v
    onSelectChatModel(id)
    onCommitChatModel?.(id)
  }

  const hasActiveCaps = capabilities.reflection || capabilities.research || capabilities.web
  const canSubmit = !composerDisabled && !streaming && composeDraft.trim().length > 0

  return (
    <>
      <RequestAccessModal
        model={requestAccessModel}
        open={requestAccessModel != null}
        onClose={() => setRequestAccessModel(null)}
      />
      <ModelTuningModal
        model={selectedCatalogModel}
        open={tuningOpen}
        onClose={() => setTuningOpen(false)}
        tuning={tuning}
        onTuningChange={onTuningChange}
      />

      {/* Capability sheet */}
      {capsOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/30"
          onClick={() => setCapsOpen(false)}
          aria-hidden
        />
      )}
      {capsOpen && (
        <div className="fixed bottom-0 inset-x-0 z-50 rounded-t-2xl border-t border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-950">
          <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-neutral-300 dark:bg-neutral-700" />
          <p className="px-4 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wide text-neutral-400">
            Capabilities
          </p>
          {CAPABILITY_MENU.map(({ key, label }) => {
            const on = capabilities[key]
            return (
              <button
                key={key}
                type="button"
                disabled={capabilityDisabled}
                onClick={() => { onToggleCapability(key); setCapsOpen(false) }}
                className="flex w-full items-center justify-between px-4 py-3.5 text-sm text-neutral-800 hover:bg-neutral-50 disabled:opacity-50 dark:text-neutral-200 dark:hover:bg-neutral-900"
              >
                <span className={on ? 'font-semibold' : ''}>{label}</span>
                {on && (
                  <span className="size-2 rounded-full bg-neutral-900 dark:bg-neutral-100" />
                )}
              </button>
            )
          })}
          <div style={{ paddingBottom: 'env(safe-area-inset-bottom)' }} className="pb-2" />
        </div>
      )}

      <div className="border-t border-neutral-200 bg-white px-3 pt-2 pb-2 dark:border-neutral-800 dark:bg-neutral-950"
        style={{ paddingBottom: 'max(0.5rem, env(safe-area-inset-bottom))' }}
      >
        {/* Active capability tags */}
        {hasActiveCaps && (
          <div className="mb-2 flex flex-wrap gap-1">
            {capabilities.reflection && (
              <CapabilityTag label="Reflection" disabled={capabilityDisabled} onRemove={() => onToggleCapability('reflection')} />
            )}
            {capabilities.research && (
              <CapabilityTag label="Research" disabled={capabilityDisabled} onRemove={() => onToggleCapability('research')} />
            )}
            {capabilities.web && (
              <CapabilityTag label="Web stance" disabled={capabilityDisabled} onRemove={() => onToggleCapability('web')} />
            )}
          </div>
        )}

        {/* Attachment chips */}
        {((pendingServerAttachments?.length ?? 0) > 0 || (pendingLocalFileNames?.length ?? 0) > 0) && (
          <div className="mb-2 flex flex-wrap gap-1">
            {pendingServerAttachments?.map((a) => (
              <span key={`srv-${a.id}`} className="inline-flex max-w-[min(100%,14rem)] items-center gap-1 truncate rounded-md border border-neutral-200 bg-neutral-50 px-2 py-0.5 text-xs text-neutral-800 dark:border-neutral-600 dark:bg-neutral-900 dark:text-neutral-200">
                <span className="min-w-0 truncate">{a.name}</span>
                <button type="button" className="shrink-0 rounded p-0.5 text-neutral-500 hover:bg-neutral-200 dark:hover:bg-neutral-800" aria-label={`Remove ${a.name}`} disabled={Boolean(attachDisabled) || streaming} onClick={() => onRemoveServerAttachment?.(a.id)}>
                  <X className="size-3" strokeWidth={2.5} />
                </button>
              </span>
            ))}
            {pendingLocalFileNames?.map((name, i) => (
              <span key={`loc-${i}-${name}`} className="inline-flex max-w-[min(100%,14rem)] items-center gap-1 truncate rounded-md border border-neutral-200 bg-neutral-50 px-2 py-0.5 text-xs text-neutral-800 dark:border-neutral-600 dark:bg-neutral-900 dark:text-neutral-200">
                <span className="min-w-0 truncate">{name}</span>
                <button type="button" className="shrink-0 rounded p-0.5 text-neutral-500 hover:bg-neutral-200 dark:hover:bg-neutral-800" aria-label={`Remove ${name}`} disabled={Boolean(attachDisabled) || streaming} onClick={() => onRemoveLocalFile?.(i)}>
                  <X className="size-3" strokeWidth={2.5} />
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Textarea pill */}
        <div className={`flex items-end gap-2 rounded-2xl border px-3 py-2 ${inputThemed}`}>
          <textarea
            ref={composeTextareaRef}
            className="min-h-0 flex-1 resize-none bg-transparent text-sm leading-snug outline-none placeholder:text-neutral-400"
            value={composeDraft}
            onChange={(e) => setComposeDraft(e.target.value)}
            onKeyDown={(e) => {
              // Mobile: Enter = newline. No keyboard submit.
              if (e.key === 'Enter' && e.shiftKey) {
                e.preventDefault()
              }
            }}
            placeholder="Message…"
            disabled={Boolean(composerDisabled) || streaming}
            rows={1}
            maxLength={maxInputChars}
            aria-label="Message"
          />
          {streaming ? (
            <button
              type="button"
              className="mb-0.5 flex size-8 shrink-0 items-center justify-center rounded-full border border-red-300 text-red-700 dark:border-red-800 dark:text-red-400"
              aria-label="Stop generating"
              onClick={onStop}
            >
              <Square className="size-3.5 fill-current" strokeWidth={2} />
            </button>
          ) : (
            <button
              type="button"
              className="mb-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-neutral-900 text-white shadow-sm disabled:opacity-40 dark:bg-neutral-100 dark:text-neutral-900"
              disabled={!canSubmit}
              aria-label="Send message"
              onClick={onSubmit}
            >
              <ArrowUp className="size-4" strokeWidth={2.5} />
            </button>
          )}
        </div>

        {/* Icon tray */}
        <div className="mt-2 flex items-center gap-2">
          {onLocalFilesChosen != null && (
            <>
              <input
                ref={attachInputRef}
                type="file"
                multiple
                className="sr-only"
                accept=".txt,.md,text/plain,text/markdown"
                disabled={Boolean(attachDisabled) || streaming}
                onChange={(e) => {
                  const files = Array.from(e.target.files ?? [])
                  e.target.value = ''
                  if (files.length) onLocalFilesChosen(files)
                }}
              />
              <button
                type="button"
                className="flex h-11 w-11 items-center justify-center rounded-xl border border-neutral-200 text-neutral-600 hover:bg-neutral-50 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-900"
                aria-label="Attach files"
                disabled={Boolean(attachDisabled) || streaming}
                onClick={() => attachInputRef.current?.click()}
              >
                <Paperclip className="size-5" strokeWidth={2} />
              </button>
            </>
          )}

          <button
            type="button"
            className="flex h-11 w-11 items-center justify-center rounded-xl border border-neutral-200 text-neutral-600 hover:bg-neutral-50 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-900"
            aria-label="Toggle capabilities"
            disabled={capabilityDisabled}
            onClick={() => setCapsOpen(true)}
          >
            <Sparkles className="size-5" strokeWidth={2} />
          </button>

          <div className="min-w-0 flex-1">
            <label className="sr-only" htmlFor="chat-model-select-mobile">Model</label>
            <Select
              open={modelSelectOpen}
              onOpenChange={setModelSelectOpen}
              value={selectValue || undefined}
              onValueChange={handleModelSelectChange}
              disabled={modelSelectDisabled || modelsPending || sorted.length === 0}
            >
              <SelectTrigger
                id="chat-model-select-mobile"
                data-testid="chat-model-select"
                title={modelLabel}
                className="h-11 w-full border-neutral-200 px-3 text-xs dark:border-neutral-700 [&_svg]:size-3"
              >
                <SelectValue placeholder={modelLabel} />
              </SelectTrigger>
              <SelectContent position="popper" side="top" sideOffset={6} align="start">
                {!modelsPending &&
                  sorted.map((m) =>
                    m.accessible ? (
                      <SelectItem key={m.id} value={`${CATALOG_SELECT_PREFIX}${m.slug}`} textValue={m.display_name}>
                        {m.display_name}
                      </SelectItem>
                    ) : (
                      <SelectItem key={m.id} value={`${CATALOG_SELECT_PREFIX}${m.slug}`} disabled textValue={m.display_name}>
                        {m.display_name} (locked)
                      </SelectItem>
                    ),
                  )}
              </SelectContent>
            </Select>
            {modelsError && (
              <p className="mt-0.5 text-[10px] text-amber-600 dark:text-amber-400">Catalog failed</p>
            )}
          </div>

          {kbSlot != null && <div className="shrink-0">{kbSlot}</div>}

          <button
            type="button"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-neutral-200 text-neutral-600 hover:bg-neutral-50 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-900"
            aria-label="Model settings"
            disabled={!selectedCatalogModel}
            onClick={() => {
              if (selectedCatalogModel) onTuningChange(defaultTuningFromCatalog(selectedCatalogModel))
              setTuningOpen(true)
            }}
          >
            <Settings2 className="size-5" strokeWidth={2} />
          </button>
        </div>
      </div>
    </>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/chat/ChatComposerDockMobile.tsx
git commit -m "feat(mobile): add ChatComposerDockMobile (iMessage-style)"
```

---

## Task 9: Wire mobile composer into `ConversationThreadPage`

**Files:**
- Modify: `frontend/src/components/chat/ConversationThreadPage.tsx`

- [ ] **Step 1: Import mobile composer and `useIsMobile`, swap in the thread page**

In `ConversationThreadPage.tsx`, add these imports at the top:

```tsx
import { useIsMobile } from '~/hooks/useIsMobile'
import { ChatComposerDockMobile } from '~/components/chat/ChatComposerDockMobile'
```

Find where `<ChatComposerDock` is rendered (there will be one usage). Replace it with a conditional:

```tsx
const isMobile = useIsMobile()

// Replace the <ChatComposerDock ... /> JSX with:
{isMobile ? (
  <ChatComposerDockMobile
    models={modelsQ.data}
    modelsPending={modelsQ.isPending}
    modelsError={modelsQ.error as Error | null}
    chatModel={chatModel}
    onSelectChatModel={setModelDraft}
    onCommitChatModel={handleCommitModel}
    modelSelectDisabled={streaming}
    capabilities={capabilities}
    onToggleCapability={handleToggleCapability}
    capabilityDisabled={streaming}
    composeDraft={composeDraft}
    setComposeDraft={setComposeDraft}
    onSubmit={handleSubmit}
    streaming={streaming}
    onStop={handleStop}
    inputThemed={inputThemed}
    composerDisabled={composerDisabled}
    kbSlot={kbSlot}
    selectedCatalogModel={selectedCatalogModel}
    tuning={tuning}
    onTuningChange={setTuning}
    pendingServerAttachments={pendingServerAttachments}
    pendingLocalFileNames={pendingLocalFileNames}
    onRemoveServerAttachment={handleRemoveServerAttachment}
    onRemoveLocalFile={handleRemoveLocalFile}
    onLocalFilesChosen={handleLocalFilesChosen}
    attachDisabled={attachDisabled}
  />
) : (
  <ChatComposerDock
    {/* ... existing props unchanged ... */}
  />
)}
```

Note: The exact prop names (`handleCommitModel`, `handleToggleCapability`, `handleSubmit`, etc.) must match what already exists in the file. Read the file to confirm all prop names before editing.

Also update message bubble max-width for mobile. Find `max-w-[70%]` or similar on message bubble containers and change to `max-w-[85%] md:max-w-[70%]`.

- [ ] **Step 2: Add keyboard avoidance via `visualViewport`**

In `ConversationThreadPage.tsx`, add a `useEffect` that shifts the composer above the soft keyboard on mobile. Add this inside the component (near other refs/effects):

```tsx
const composerRef = React.useRef<HTMLDivElement>(null)

React.useEffect(() => {
  if (!isMobile) return
  const vv = window.visualViewport
  if (!vv) return
  const onResize = () => {
    const el = composerRef.current
    if (!el) return
    const offsetFromBottom = window.innerHeight - (vv.offsetTop + vv.height)
    el.style.paddingBottom = offsetFromBottom > 0 ? `${offsetFromBottom}px` : ''
  }
  vv.addEventListener('resize', onResize)
  vv.addEventListener('scroll', onResize)
  return () => {
    vv.removeEventListener('resize', onResize)
    vv.removeEventListener('scroll', onResize)
  }
}, [isMobile])
```

Wrap the composer JSX in `<div ref={composerRef}>`.

- [ ] **Step 3: Verify on mobile viewport**

At 375px: iMessage-style composer with pill textarea and icon tray. At 768px+: original flat toolbar composer.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/chat/ConversationThreadPage.tsx
git commit -m "feat(mobile): use ChatComposerDockMobile on small screens"
```

---

## Task 10: Page transitions — add `page-enter` to route root elements

**Files:**
- Modify: `frontend/src/components/home/HomePage.tsx`
- Modify: `frontend/src/components/memories/MemoriesPage.tsx`
- Modify: `frontend/src/routes/knowledge-bases/index.tsx`
- Modify: `frontend/src/routes/knowledge-bases/$id.tsx`
- Modify: `frontend/src/components/chat/ConversationThreadPage.tsx`

- [ ] **Step 1: Add `page-enter` class to each page's root element**

For each file, find the outermost `<div` returned from the component and add `page-enter` to its `className`. Examples:

`HomePage.tsx` — root div:
```tsx
<div className="page-enter mx-auto min-h-0 w-full max-w-4xl flex-1 space-y-8 overflow-y-auto overscroll-contain p-4 md:p-6">
```

`MemoriesPage.tsx` — find root div and add `page-enter`:
```tsx
<div className="page-enter mx-auto ...">
```

`knowledge-bases/index.tsx` — root div:
```tsx
<div className="page-enter mx-auto flex min-h-0 w-full max-w-6xl flex-1 flex-col gap-4 overflow-hidden p-4 sm:p-6">
```

`ConversationThreadPage.tsx` — root wrapper div, add `page-enter`.

- [ ] **Step 2: Verify transitions feel snappy**

Navigate between tabs on mobile. Pages should fade in with a subtle 6px upward slide over 150ms.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/home/HomePage.tsx \
        frontend/src/components/memories/MemoriesPage.tsx \
        frontend/src/routes/knowledge-bases/index.tsx \
        frontend/src/routes/knowledge-bases/'$id'.tsx \
        frontend/src/components/chat/ConversationThreadPage.tsx
git commit -m "feat(mobile): add page-enter transition to route pages"
```

---

## Task 11: Responsive page adaptations

**Files:**
- Modify: `frontend/src/components/home/HomePage.tsx`
- Modify: `frontend/src/components/memories/MemoriesPage.tsx`
- Modify: `frontend/src/routes/knowledge-bases/index.tsx`

- [ ] **Step 1: `HomePage` — responsive padding**

Change the root div padding from `p-6` to `p-4 md:p-6` (already in Task 10 above — confirm it's applied).

- [ ] **Step 2: `MemoriesPage` — responsive padding and single-column stack**

Find the root div and ensure `p-4 md:p-6`. If memory cards or table rows use a fixed min-width that overflows, ensure the table container has `overflow-x-auto`.

- [ ] **Step 3: `KnowledgeBasesIndexPage` — add mobile card list view**

In `knowledge-bases/index.tsx`, wrap the existing `<TableShell>` in a `hidden md:flex md:flex-col` div. Add a mobile card list above it:

```tsx
{/* Mobile card list — visible below md */}
{filteredRows.length > 0 && (
  <div className="flex flex-col gap-2 md:hidden">
    {filteredRows.map((kb) => (
      <Link
        key={kb.id}
        to="/knowledge-bases/$id"
        params={{ id: String(kb.id) }}
        className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-medium text-neutral-900 dark:text-neutral-100">{kb.name}</p>
            {kb.description && (
              <p className="mt-0.5 line-clamp-2 text-xs text-neutral-600 dark:text-neutral-400">
                {kb.description}
              </p>
            )}
          </div>
          <Eye className="mt-0.5 size-4 shrink-0 text-neutral-400" aria-hidden />
        </div>
        <div className="mt-2 flex flex-wrap gap-2 text-xs text-neutral-500 dark:text-neutral-400">
          <span>{(kb.document_count ?? 0).toLocaleString()} docs</span>
          <span>{(kb.chunks_count ?? 0).toLocaleString()} chunks</span>
          <span>{formatBytes(kb.size_bytes)}</span>
          <span>{formatDate(kb.created_at)}</span>
        </div>
      </Link>
    ))}
  </div>
)}

{/* Desktop table — hidden below md */}
<div className="hidden md:flex md:min-h-0 md:flex-1 md:flex-col">
  <TableShell containerRef={tableScrollRef}>
    {/* ... existing table unchanged ... */}
  </TableShell>
</div>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/home/HomePage.tsx \
        frontend/src/components/memories/MemoriesPage.tsx \
        frontend/src/routes/knowledge-bases/index.tsx
git commit -m "feat(mobile): responsive page adaptations (padding, KB card list)"
```

---

## Task 12: Modals as bottom sheets on mobile

**Files:**
- Modify: `frontend/src/components/knowledge-bases/CreateKnowledgeBaseDialog.tsx`
- Modify: `frontend/src/components/chat/ModelTuningModal.tsx`

- [ ] **Step 1: Read `CreateKnowledgeBaseDialog.tsx` to understand current structure**

The dialog likely uses a `<dialog>` element or a custom modal wrapper. The goal: on mobile, instead of a centered overlay, render as a bottom sheet: `fixed bottom-0 inset-x-0 rounded-t-2xl`.

- [ ] **Step 2: Update `CreateKnowledgeBaseDialog` modal container**

Find the dialog container div (the white panel, not the backdrop). Add responsive classes:

```tsx
// Before (example — confirm actual class):
<div className="relative rounded-xl bg-white p-6 shadow-xl ...">

// After:
<div className="relative w-full rounded-t-2xl bg-white p-4 shadow-xl md:max-w-lg md:rounded-xl md:p-6 ...">
```

And the backdrop/positioning wrapper:

```tsx
// Before (example):
<div className="fixed inset-0 z-50 flex items-center justify-center p-4">

// After:
<div className="fixed inset-0 z-50 flex items-end justify-center md:items-center md:p-4">
```

Add drag handle on mobile:

```tsx
<div className="mx-auto mb-4 h-1 w-10 rounded-full bg-neutral-300 dark:bg-neutral-700 md:hidden" />
```

- [ ] **Step 3: Apply the same pattern to `ModelTuningModal`**

Same approach: `items-end` on mobile, `md:items-center md:p-4` on desktop. Add drag handle, remove top padding on mobile panel.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/knowledge-bases/CreateKnowledgeBaseDialog.tsx \
        frontend/src/components/chat/ModelTuningModal.tsx
git commit -m "feat(mobile): modals render as bottom sheets on mobile"
```

---

## Task 13: E2E tests for mobile

**Files:**
- Create: `frontend/e2e/mobile-nav.spec.ts`

- [ ] **Step 1: Check E2E setup**

```bash
cat frontend/e2e/global-setup.ts
cat frontend/package.json | grep -A5 '"e2e"'
```

Note the base URL and any auth setup used by existing tests.

- [ ] **Step 2: Write E2E tests**

```typescript
// frontend/e2e/mobile-nav.spec.ts
import { test, expect } from '@playwright/test'

const MOBILE_VIEWPORT = { width: 375, height: 812 }

test.describe('mobile navigation', () => {
  test.use({ viewport: MOBILE_VIEWPORT })

  test('bottom tab bar is visible on mobile', async ({ page }) => {
    await page.goto('/')
    const nav = page.getByRole('navigation', { name: 'Main navigation' })
    await expect(nav).toBeVisible()
    await expect(page.getByRole('link', { name: 'Home' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Chat' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'KBs' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Memories' })).toBeVisible()
  })

  test('desktop sidebar is hidden on mobile', async ({ page }) => {
    await page.goto('/')
    const sidebar = page.getByRole('complementary', { name: 'Main navigation' })
    await expect(sidebar).not.toBeVisible()
  })

  test('More tab opens bottom sheet with overflow items', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'More navigation options' }).click()
    await expect(page.getByText('Org Settings')).toBeVisible()
    // Close by tapping backdrop
    await page.mouse.click(10, 10)
    await expect(page.getByText('Org Settings')).not.toBeVisible()
  })

  test('tab navigation works', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('link', { name: 'KBs' }).click()
    await expect(page).toHaveURL(/\/knowledge-bases/)
    await page.getByRole('link', { name: 'Memories' }).click()
    await expect(page).toHaveURL(/\/memories/)
  })
})

test.describe('mobile conversation drawer', () => {
  test.use({ viewport: MOBILE_VIEWPORT })

  test('hamburger opens conversation drawer', async ({ page }) => {
    await page.goto('/chat/conversations')
    await page.getByRole('button', { name: 'Open conversations' }).click()
    await expect(page.getByRole('dialog', { name: 'Conversations' })).toBeVisible()
  })

  test('drawer closes on backdrop tap', async ({ page }) => {
    await page.goto('/chat/conversations')
    await page.getByRole('button', { name: 'Open conversations' }).click()
    const dialog = page.getByRole('dialog', { name: 'Conversations' })
    await expect(dialog).toBeVisible()
    // Click to the right of the drawer (backdrop)
    await page.mouse.click(370, 200)
    await expect(dialog).not.toBeVisible()
  })

  test('drawer closes on X button', async ({ page }) => {
    await page.goto('/chat/conversations')
    await page.getByRole('button', { name: 'Open conversations' }).click()
    await page.getByRole('button', { name: 'Close conversations' }).click()
    await expect(page.getByRole('dialog', { name: 'Conversations' })).not.toBeVisible()
  })
})

test.describe('mobile composer', () => {
  test.use({ viewport: MOBILE_VIEWPORT })

  test('send button is disabled when input is empty', async ({ page }) => {
    await page.goto('/chat/conversations')
    const sendBtn = page.getByRole('button', { name: 'Send message' })
    await expect(sendBtn).toBeDisabled()
  })

  test('send button enables when text is typed', async ({ page }) => {
    await page.goto('/chat/conversations')
    await page.getByRole('textbox', { name: 'Message' }).fill('hello')
    const sendBtn = page.getByRole('button', { name: 'Send message' })
    await expect(sendBtn).toBeEnabled()
  })
})
```

- [ ] **Step 3: Run the E2E tests**

```bash
cd frontend && pnpm test:e2e -- --grep "mobile"
```

Fix any failures before continuing. Common issues:
- Auth redirect blocking the page — check `global-setup.ts` for how existing tests handle auth
- Selectors not matching — use `page.locator('[data-testid=...]')` if ARIA roles aren't sufficient

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/mobile-nav.spec.ts
git commit -m "test(e2e): add mobile navigation and composer E2E tests"
```

---

## Task 14: Final verification

- [ ] **Step 1: Run full E2E suite to confirm no regressions**

```bash
cd frontend && pnpm test:e2e
```

All tests must pass.

- [ ] **Step 2: Manual mobile smoke test**

Start dev server with `pnpm dev --host`. Open on a real phone or Chrome DevTools mobile emulation (375×812):

- [ ] Bottom tab bar visible, all 4 tabs navigate correctly
- [ ] More tab opens sheet, Org Settings link visible
- [ ] Chat: hamburger opens drawer, shows conversation list
- [ ] Drawer: tap outside closes, X button closes
- [ ] Drawer: new conversation button works
- [ ] Composer: pill textarea, icon tray visible
- [ ] Composer: send button disabled when empty, enabled when typing
- [ ] Capabilities sheet opens and toggles work
- [ ] Model selector works
- [ ] Page transitions visible when switching tabs (subtle fade + slide)
- [ ] Modals (KB create, model tuning) appear as bottom sheets
- [ ] KB page shows card list instead of table
- [ ] Desktop (768px+): sidebar back, no tab bar, original composer

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat(mobile): complete mobile responsive implementation"
```
