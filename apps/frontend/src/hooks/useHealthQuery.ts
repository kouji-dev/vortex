import { useQuery } from '@tanstack/react-query'

import { getApiBase } from '~/lib/api-base'
import type { HealthResponse } from '~/lib/health-types'
import { queryKeys } from '~/lib/queryKeys'

export function useHealthQuery() {
  const apiBase = getApiBase()
  return useQuery({
    queryKey: queryKeys.health(apiBase),
    queryFn: async () => {
      const res = await fetch(`${apiBase}/health`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.json() as Promise<HealthResponse>
    },
  })
}
