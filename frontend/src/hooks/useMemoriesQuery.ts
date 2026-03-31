import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

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

export interface MemoryPage {
  items: Memory[]
  next_cursor: number | null
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

export function useMemoriesInfiniteQuery(limit = 25) {
  const apiBase = getApiBase()
  return useInfiniteQuery({
    queryKey: [...queryKeys.memoriesPage(), limit] as const,
    initialPageParam: null as number | null,
    queryFn: async ({ pageParam }): Promise<MemoryPage> => {
      const qs = new URLSearchParams({ limit: String(limit) })
      if (pageParam != null) qs.set('cursor', String(pageParam))
      const res = await fetch(`${apiBase}/api/users/me/memories/page?${qs.toString()}`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.json()
    },
    getNextPageParam: (lastPage) => lastPage.next_cursor,
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
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.memories() })
      void qc.invalidateQueries({ queryKey: queryKeys.memoriesPage() })
    },
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
    onSuccess: (updated) => {
      qc.setQueryData<Memory[] | undefined>(queryKeys.memories(), (prev) =>
        prev ? prev.map((m) => (m.id === updated.id ? updated : m)) : prev,
      )
      qc.setQueriesData(
        { queryKey: queryKeys.memoriesPage() },
        (prev: { pages: MemoryPage[]; pageParams: Array<number | null> } | undefined) => {
          if (!prev) return prev
          return {
            ...prev,
            pages: prev.pages.map((page) => ({
              ...page,
              items: page.items.map((m) => (m.id === updated.id ? updated : m)),
            })),
          }
        },
      )
    },
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
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.memories() })
      void qc.invalidateQueries({ queryKey: queryKeys.memoriesPage() })
    },
  })
}
