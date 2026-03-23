import { useQuery } from '@tanstack/react-query'

import { getApiBase } from '~/lib/api-base'
import type { Conversation } from '~/lib/chat-types'
import { queryKeys } from '~/lib/queryKeys'
import { getAuthHeaders } from '~/lib/authorizedFetch'

export function useConversationsListQuery() {
  const apiBase = getApiBase()
  return useQuery({
    queryKey: queryKeys.conversations(),
    queryFn: async () => {
      const res = await fetch(`${apiBase}/api/chat/conversations`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.json() as Promise<Conversation[]>
    },
  })
}
