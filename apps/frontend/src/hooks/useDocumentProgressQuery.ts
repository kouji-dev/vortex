import { useQuery } from '@tanstack/react-query'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import { queryKeys } from '~/lib/queryKeys'

export interface DocumentProgress {
  document_id: number
  status: string
  chunks_done: number
  chunks_total: number | null
  ingest_error?: string | null
}

export function useDocumentProgressQuery(
  kbId: number,
  docId: number,
  options: { enabled?: boolean } = {},
) {
  const apiBase = getApiBase()
  return useQuery({
    queryKey: queryKeys.documentProgress(kbId, docId),
    queryFn: async (): Promise<DocumentProgress> => {
      const res = await fetch(
        `${apiBase}/api/knowledge-bases/${kbId}/documents/${docId}/progress`,
        { headers: await getAuthHeaders() },
      )
      if (!res.ok) throw new Error(`Progress fetch failed: ${res.status}`)
      return res.json()
    },
    enabled: options.enabled ?? true,
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return 1500
      return data.status === 'ingesting' || data.status === 'pending' ? 1500 : false
    },
  })
}
