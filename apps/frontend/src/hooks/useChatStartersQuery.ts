import { useQuery } from '@tanstack/react-query'

import { getApiBase } from '~/lib/api-base'
import { queryKeys } from '~/lib/queryKeys'
import { getAuthHeaders } from '~/lib/authorizedFetch'

export type ChatStartersPayload = {
  sections: {
    title: string
    prompts: string[]
    links?: { label: string; href: string }[]
  }[]
}

export function useChatStartersQuery(enabled: boolean) {
  const apiBase = getApiBase()
  return useQuery({
    queryKey: queryKeys.chatStarters(),
    enabled,
    queryFn: async () => {
      const res = await fetch(`${apiBase}/api/chat/starters`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.json() as Promise<ChatStartersPayload>
    },
  })
}
