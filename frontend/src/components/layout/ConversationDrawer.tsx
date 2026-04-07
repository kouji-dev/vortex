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
            hideHeader
          />
        </div>
      </div>
    </>
  )
}
