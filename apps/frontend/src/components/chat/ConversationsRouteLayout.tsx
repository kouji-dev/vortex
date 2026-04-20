import { Outlet, useLocation, useNavigate } from '@tanstack/react-router'
import * as React from 'react'

import { ConversationInspectorPanel } from '~/components/chat/ConversationInspectorPanel'
import { ConversationsSidebarPanel } from '~/components/chat/ConversationsSidebarPanel'
import { useChatStartersQuery } from '~/hooks/useChatStartersQuery'
import { useConversationsListQuery } from '~/hooks/useConversationsListQuery'
import { ConversationsOutletProvider } from '~/contexts/ConversationsOutletContext'
import type { ThreadItem } from '~/lib/chat-types'

export function ConversationsRouteLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const [composeDraft, setComposeDraft] = React.useState('')
  const [inspectorOpen, setInspectorOpen] = React.useState(false)
  const [activeMessage, setActiveMessage] = React.useState<ThreadItem | null>(null)

  const loadStarters = location.pathname.startsWith('/chat/conversations')

  const convsQ = useConversationsListQuery()
  const startersQ = useChatStartersQuery(loadStarters)

  const outletValue = React.useMemo(
    () => ({
      composeDraft,
      setComposeDraft,
      chatStarters: startersQ.data,
      chatStartersFetched: startersQ.isFetched,
      inspectorOpen,
      setInspectorOpen,
      activeMessage,
      setActiveMessage,
    }),
    [composeDraft, startersQ.data, startersQ.isFetched, inspectorOpen, activeMessage],
  )

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
