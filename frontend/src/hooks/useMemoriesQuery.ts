import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import { queryKeys } from '~/lib/queryKeys'

export interface Memory {
  id: number
  content: string
  source: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export function useMemoriesQuery() {
  const apiBase = getApiBase()
  return useQuery({
    queryKey: queryKeys.memories(),
    queryFn: async (): Promise<Memory[]> => {
      const res = await fetch(`${apiBase}/api/users/me/memories`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.json()
    },
  })
}

export function useCreateMemory() {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (content: string): Promise<Memory> => {
      const res = await fetch(`${apiBase}/api/users/me/memories`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(await getAuthHeaders()) },
        body: JSON.stringify({ content }),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json()
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.memories() }),
  })
}

export function useUpdateMemory() {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      id,
      ...body
    }: { id: number; content?: string; is_active?: boolean }): Promise<Memory> => {
      const res = await fetch(`${apiBase}/api/users/me/memories/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...(await getAuthHeaders()) },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json()
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.memories() }),
  })
}

export function useDeleteMemory() {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: number): Promise<void> => {
      const res = await fetch(`${apiBase}/api/users/me/memories/${id}`, {
        method: 'DELETE',
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(await res.text())
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.memories() }),
  })
}
