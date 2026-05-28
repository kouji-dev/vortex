/**
 * Q1 — Knowledge bases list.
 *
 * Mirrors the existing `/knowledge-bases` list but lives under `/rag` so the
 * sidebar navigation works. Click a KB → drills into per-KB sub-pages.
 */
import { useInfiniteQuery } from '@tanstack/react-query'
import { Link, createFileRoute } from '@tanstack/react-router'
import * as React from 'react'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import type { KnowledgeBaseSummary } from '~/lib/knowledge-base-types'
import { queryKeys } from '~/lib/queryKeys'

export const Route = createFileRoute('/rag/kbs/')({
  component: KbsPage,
})

function KbsPage() {
  const apiBase = getApiBase()
  const [search, setSearch] = React.useState('')

  const listQ = useInfiniteQuery({
    queryKey: queryKeys.knowledgeBasesPage(),
    initialPageParam: null as number | null,
    queryFn: async ({ pageParam }) => {
      const qs = new URLSearchParams({ limit: '25' })
      if (pageParam != null) qs.set('cursor', String(pageParam))
      const res = await fetch(`${apiBase}/api/knowledge-bases/page?${qs.toString()}`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json() as Promise<{
        items: KnowledgeBaseSummary[]
        next_cursor: number | null
      }>
    },
    getNextPageParam: (p) => p.next_cursor,
  })

  const all = (listQ.data?.pages ?? []).flatMap((p) => p.items)
  const filtered = search
    ? all.filter((kb) => kb.name.toLowerCase().includes(search.toLowerCase()))
    : all

  return (
    <div className="panel" data-testid="rag-kbs">
      <div className="panel-head">
        <span>Knowledge bases</span>
        <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>{all.length} total</span>
      </div>
      <div className="panel-body" style={{ padding: 12 }}>
        <input
          className="rag-input"
          placeholder="Filter by name"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ marginBottom: 8 }}
          data-testid="rag-kbs-search"
        />
        {listQ.isPending && (
          <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>
        )}
        <table className="rag-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Docs</th>
              <th>Chunks</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {filtered.map((kb) => (
              <tr key={kb.id} data-testid={`rag-kbs-row-${kb.id}`}>
                <td>{kb.name}</td>
                <td>{kb.document_count ?? '—'}</td>
                <td>{kb.chunks_count ?? '—'}</td>
                <td>{new Date(kb.created_at).toLocaleDateString()}</td>
                <td>
                  <Link to="/rag/kbs/$id/overview" params={{ id: String(kb.id) }}>
                    Open
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!filtered.length && !listQ.isPending && (
          <p style={{ fontSize: 12, color: 'var(--ink-3)', textAlign: 'center', padding: 16 }}>
            No knowledge bases.
          </p>
        )}
        {listQ.hasNextPage && (
          <button
            type="button"
            onClick={() => void listQ.fetchNextPage()}
            disabled={listQ.isFetchingNextPage}
            style={{ marginTop: 8 }}
          >
            {listQ.isFetchingNextPage ? 'Loading…' : 'Load more'}
          </button>
        )}
      </div>
    </div>
  )
}
