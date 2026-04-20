import { Outlet, useLocation, useNavigate } from '@tanstack/react-router'
import * as React from 'react'

import { ConversationInspectorPanel } from '~/components/chat/ConversationInspectorPanel'
import { ConversationsSidebarPanel } from '~/components/chat/ConversationsSidebarPanel'
import { useConversationsListQuery } from '~/hooks/useConversationsListQuery'
import { useIsMobile } from '~/hooks/useIsMobile'
import { ConversationsOutletProvider } from '~/contexts/ConversationsOutletContext'
import type { ThreadItem } from '~/lib/chat-types'

const THREAD_PATH_RE = /^\/chat\/conversations\/\d+/

export function ConversationsRouteLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { isMobile } = useIsMobile()
  const [composeDraft, setComposeDraft] = React.useState('')
  const [inspectorOpen, setInspectorOpen] = React.useState(false)
  const [activeMessage, setActiveMessage] = React.useState<ThreadItem | null>(null)

  const isThreadRoute = THREAD_PATH_RE.test(location.pathname)
  const convsQ = useConversationsListQuery()

  const outletValue = React.useMemo(
    () => ({
      composeDraft,
      setComposeDraft,
      inspectorOpen,
      setInspectorOpen,
      activeMessage,
      setActiveMessage,
    }),
    [composeDraft, inspectorOpen, activeMessage],
  )

  // Mobile: master/detail. Index route = full-screen list; ?compose=1 = composer.
  // :id route = full-screen thread. No inline sidebar next to thread.
  const composeMode = (location.search as Record<string, unknown>)?.compose === '1'

  if (isMobile) {
    return (
      <ConversationsOutletProvider value={outletValue}>
        <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col" data-testid="chat-layout">
          {isThreadRoute || composeMode ? (
            <Outlet />
          ) : (
            <ConversationsSidebarPanel
              conversations={convsQ.data}
              conversationsPending={convsQ.isPending}
              conversationsError={convsQ.error as Error | null}
              onNewConversation={() => {
                void navigate({ to: '/chat/conversations', search: { compose: '1' } })
              }}
            />
          )}
        </div>
      </ConversationsOutletProvider>
    )
  }

  return (
    <ConversationsOutletProvider value={outletValue}>
      <div
        className={`chat-grid ${inspectorOpen ? '' : 'chat-grid-2col'}`}
        data-testid="chat-layout"
      >
        <ConversationsSidebarPanel
          conversations={convsQ.data}
          conversationsPending={convsQ.isPending}
          conversationsError={convsQ.error as Error | null}
          onNewConversation={() => {
            void navigate({ to: '/chat/conversations' })
          }}
        />
        <Outlet />
        {inspectorOpen && <ConversationInspectorPanel />}
      </div>
    </ConversationsOutletProvider>
  )
}
