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

  const handleNewConversation = React.useCallback(() => {
    void navigate({ to: '/chat/conversations' })
  }, [navigate])

  const handleCloseDrawer = React.useCallback(() => setDrawerOpen(false), [])

  const handleOpenDrawer = React.useCallback(() => setDrawerOpen(true), [])

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-panel">
      <MobileHeader
        conversationTitle={conversationTitle}
        onOpenDrawer={handleOpenDrawer}
        onNewConversation={handleNewConversation}
      />

      <ConversationDrawer
        open={drawerOpen}
        onClose={handleCloseDrawer}
        conversations={convsQ.data}
        conversationsPending={convsQ.isPending}
        conversationsError={convsQ.error as Error | null}
        onNewConversation={handleNewConversation}
      />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        {children}
      </div>

      <BottomTabBar />
    </div>
  )
}
