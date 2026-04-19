import { useQuery } from '@tanstack/react-query'

import { getApiBase } from '~/lib/api-base'
import type { Conversation } from '~/lib/chat-types'
import { queryKeys } from '~/lib/queryKeys'
import { getAuthHeaders } from '~/lib/authorizedFetch'

export function useConversationQuery(conversationId: number | null) {
  const apiBase = getApiBase()
  return useQuery({
    queryKey:
      conversationId == null
        ? (['conversation', 'none'] as const)
        : queryKeys.conversation(conversationId),
    queryFn: async () => {
      if (conversationId == null) throw new Error('No conversation id')
      const res = await fetch(`${apiBase}/api/chat/conversations/${conversationId}`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json() as Promise<Conversation>
    },
    enabled: conversationId != null && Number.isFinite(conversationId),
  })
}
