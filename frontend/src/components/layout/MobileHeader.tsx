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
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-line bg-panel px-3">
        <button
          type="button"
          onClick={onOpenDrawer}
          className="rounded p-2 text-ink-2 hover:bg-bg-2"
          aria-label="Open conversations"
        >
          <Menu className="size-5" aria-hidden />
        </button>
        <span className="flex-1 truncate text-sm font-semibold text-ink">
          {conversationTitle ?? 'New conversation'}
        </span>
        <button
          type="button"
          onClick={onNewConversation}
          className="rounded p-2 text-ink-2 hover:bg-bg-2"
          aria-label="New conversation"
        >
          <SquarePen className="size-5" aria-hidden />
        </button>
      </header>
    )
  }

  return (
    <header className="flex h-12 shrink-0 items-center border-b border-line bg-panel px-4">
      {/* Brand — same markup as AppTopbar's .brand for visual consistency */}
      <Link to="/" className="brand" aria-label="Home" style={{ width: 'auto', borderRight: 'none', padding: '0' }}>
        <span className="brand-mark" aria-hidden>VX</span>
        <span className="brand-name">Vortex</span>
      </Link>
    </header>
  )
}
