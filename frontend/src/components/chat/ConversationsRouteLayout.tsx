import { Outlet, useLocation, useNavigate } from '@tanstack/react-router'
import * as React from 'react'

import { ConversationsSidebarPanel } from '~/components/chat/ConversationsSidebarPanel'
import { useChatStartersQuery } from '~/hooks/useChatStartersQuery'
import { useConversationsListQuery } from '~/hooks/useConversationsListQuery'
import { ConversationsOutletProvider } from '~/contexts/ConversationsOutletContext'

export function ConversationsRouteLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const [composeDraft, setComposeDraft] = React.useState('')

  const loadStarters = location.pathname.startsWith('/chat/conversations')

  const convsQ = useConversationsListQuery()
  const startersQ = useChatStartersQuery(loadStarters)

  const outletValue = React.useMemo(
    () => ({
      composeDraft,
      setComposeDraft,
      chatStarters: startersQ.data,
      chatStartersFetched: startersQ.isFetched,
    }),
    [composeDraft, startersQ.data, startersQ.isFetched],
  )

  return (
    <ConversationsOutletProvider value={outletValue}>
      <div className="page-enter flex min-h-0 flex-1 flex-col overflow-hidden md:flex-row">
        <div className="hidden md:flex md:min-h-0 md:flex-col md:shrink-0">
          <ConversationsSidebarPanel
            conversations={convsQ.data}
            conversationsPending={convsQ.isPending}
            conversationsError={convsQ.error as Error | null}
            onNewConversation={() => {
              void navigate({ to: '/chat/conversations' })
            }}
          />
        </div>
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden p-2 md:p-4">
          <Outlet />
        </div>
      </div>
    </ConversationsOutletProvider>
  )
}
