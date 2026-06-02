import { useQuery } from '@tanstack/react-query'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import type { CatalogModelEntry } from '~/lib/chat-types'

/** Catalog models flagged usable_in_worker — the source for the worker model select. */
export function useWorkerModelsQuery() {
  const apiBase = getApiBase()
  return useQuery({
    queryKey: ['catalog', 'worker-models'],
    queryFn: async (): Promise<CatalogModelEntry[]> => {
      const res = await fetch(`${apiBase}/api/models?usable_in_worker=true`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json() as Promise<CatalogModelEntry[]>
    },
  })
}
