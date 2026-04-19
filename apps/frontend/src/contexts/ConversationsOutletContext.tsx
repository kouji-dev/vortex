import * as React from 'react'

import type { ChatStartersPayload } from '~/hooks/useChatStartersQuery'

export type ConversationsOutletContextValue = {
  composeDraft: string
  setComposeDraft: React.Dispatch<React.SetStateAction<string>>
  chatStarters: ChatStartersPayload | undefined
  /** True once the starters query has finished (success or error). */
  chatStartersFetched: boolean
}

const ConversationsOutletCtx = React.createContext<ConversationsOutletContextValue | null>(
  null,
)

export function ConversationsOutletProvider({
  children,
  value,
}: {
  children: React.ReactNode
  value: ConversationsOutletContextValue
}) {
  return (
    <ConversationsOutletCtx.Provider value={value}>{children}</ConversationsOutletCtx.Provider>
  )
}

export function useConversationsOutlet() {
  const v = React.useContext(ConversationsOutletCtx)
  if (!v) {
    throw new Error('useConversationsOutlet must be used under /chat/conversations layout')
  }
  return v
}
