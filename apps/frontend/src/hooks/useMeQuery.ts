import { useQuery } from '@tanstack/react-query'

import { getApiBase } from '~/lib/api-base'
import type { MeResponse } from '~/lib/me-types'
import { queryKeys } from '~/lib/queryKeys'
import { authorizedFetch } from '~/lib/authorizedFetch'

/** MSAL + Bearer only run in the browser; skip during SSR. */
export function useMeQuery() {
  const apiBase = getApiBase()
  return useQuery({
    queryKey: queryKeys.me(apiBase),
    enabled: typeof window !== 'undefined',
    queryFn: async () => {
      const res = await authorizedFetch(`${apiBase}/api/me`)
      if (!res.ok) {
        let detail: string | undefined
        try {
          const body = (await res.clone().json()) as { detail?: unknown }
          if (typeof body.detail === 'string') {
            detail = body.detail
          }
        } catch {
          // ignore non-JSON bodies
        }
        throw new Error(
          detail ? `HTTP ${res.status}: ${detail}` : `HTTP ${res.status}`,
        )
      }
      return res.json() as Promise<MeResponse>
    },
  })
}
