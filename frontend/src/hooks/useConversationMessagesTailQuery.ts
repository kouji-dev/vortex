import { useQuery } from '@tanstack/react-query'

import { getApiBase } from '~/lib/api-base'
import type { ChatMessage } from '~/lib/chat-types'
import { queryKeys } from '~/lib/queryKeys'
import { getAuthHeaders } from '~/lib/authorizedFetch'

const DEFAULT_LIMIT = 100

export function useConversationMessagesTailQuery(
  conversationId: number | null,
  limit: number = DEFAULT_LIMIT,
) {
  const apiBase = getApiBase()
  return useQuery({
    queryKey:
      conversationId == null
        ? (['conversation-messages', 'none', 'recent-tail'] as const)
        : queryKeys.conversationMessagesTail(conversationId),
    queryFn: async () => {
      if (conversationId == null) throw new Error('No conversation id')
      const res = await fetch(
        `${apiBase}/api/chat/conversations/${conversationId}/messages?limit=${limit}&recent=true`,
        { headers: await getAuthHeaders() },
      )
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.json() as Promise<ChatMessage[]>
    },
    enabled: conversationId != null && Number.isFinite(conversationId),
  })
}
