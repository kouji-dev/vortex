import { useQuery } from '@tanstack/react-query'

import { getApiBase } from '~/lib/api-base'
import type { ThreadItem } from '~/lib/chat-types'
import { queryKeys } from '~/lib/queryKeys'
import { getAuthHeaders } from '~/lib/authorizedFetch'

const DEFAULT_LIMIT = 100

export function useConversationMessagesTailQuery(
  conversationId: number | null,
  limit: number = DEFAULT_LIMIT,
  opts: { enabled?: boolean; sinceId?: number } = {},
) {
  const { enabled: enabledOverride = true, sinceId } = opts
  const apiBase = getApiBase()
  return useQuery({
    queryKey:
      conversationId == null
        ? (['conversation-messages', 'none', 'recent-tail'] as const)
        : queryKeys.conversationMessagesTail(conversationId),
    queryFn: async ({ signal }) => {
      if (conversationId == null) throw new Error('No conversation id')
      let url =
        `${apiBase}/api/chat/conversations/${conversationId}/messages?limit=${limit}&recent=true`
      if (sinceId != null) url += `&since_id=${sinceId}`
      const res = await fetch(url, { headers: await getAuthHeaders(), signal })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.json() as Promise<ThreadItem[]>
    },
    enabled: enabledOverride && conversationId != null && Number.isFinite(conversationId),
    // Prevent automatic background refetches from wiping optimistic data set via
    // setQueryData during/after a stream. 30 s is long enough for the stream UX
    // to settle; cache is refreshed on next mount or explicit invalidation.
    staleTime: 30_000,
  })
}
