import { useQuery } from '@tanstack/react-query'

import { getApiBase } from '~/lib/api-base'
import { queryKeys } from '~/lib/queryKeys'
import { getAuthHeaders } from '~/lib/authorizedFetch'

export type CapabilityProfileEntry = {
  description: string
}

export type ChatCapabilityProfilePayload = {
  reflection: CapabilityProfileEntry
  research: CapabilityProfileEntry
}

export function useChatCapabilityProfileQuery(enabled: boolean) {
  const apiBase = getApiBase()
  return useQuery({
    queryKey: queryKeys.chatCapabilityProfile(),
    enabled,
    queryFn: async () => {
      const res = await fetch(`${apiBase}/api/chat/capability-profile`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.json() as Promise<ChatCapabilityProfilePayload>
    },
  })
}
