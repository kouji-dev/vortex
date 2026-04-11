// frontend/src/components/layout/MobileHeader.tsx
import { Link, useLocation } from '@tanstack/react-router'
import { Menu, SquarePen } from 'lucide-react'
import * as React from 'react'
import { PrismLogo, VortexWordmark } from '~/components/brand'

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
      <Link to="/" className="flex items-center gap-2">
        <PrismLogo state="mono-white" size={20} />
        <VortexWordmark variant="white" size={18} />
      </Link>
    </header>
  )
}
