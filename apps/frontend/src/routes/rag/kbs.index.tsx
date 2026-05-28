/**
 * Q1 — Knowledge bases list.
 *
 * Mirrors the existing `/knowledge-bases` list but lives under `/rag` so the
 * sidebar navigation works. Click a KB → drills into per-KB sub-pages.
 * Tag chips above the table AND-filter the listing.
 */
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, createFileRoute } from '@tanstack/react-router'
import * as React from 'react'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import { collectAllTags, filterByTags, toggleTag } from '~/lib/kb-tags'
import type { KnowledgeBaseSummary } from '~/lib/knowledge-base-types'
import { queryKeys } from '~/lib/queryKeys'

export const Route = createFileRoute('/rag/kbs/')({
  component: KbsPage,
})

function KbsPage() {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  const [search, setSearch] = React.useState('')
  const [activeTags, setActiveTags] = React.useState<string[]>([])
  const [cloneTarget, setCloneTarget] = React.useState<KnowledgeBaseSummary | null>(null)
  const [cloneName, setCloneName] = React.useState('')
  const [cloneIncludeDocs, setCloneIncludeDocs] = React.useState(false)

  const clone = useMutation({
    mutationFn: async (args: { srcId: number; name: string; includeDocs: boolean }) => {
      const res = await fetch(`${apiBase}/api/knowledge-bases/${args.srcId}/clone`, {
        method: 'POST',
        headers: {
          ...(await getAuthHeaders()),
          'content-type': 'application/json',
        },
        body: JSON.stringify({ name: args.name, include_documents: args.includeDocs }),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json()
    },
    onSuccess: () => {
      setCloneTarget(null)
      setCloneName('')
      setCloneIncludeDocs(false)
      void qc.invalidateQueries({ queryKey: queryKeys.knowledgeBasesPage() })
    },
  })

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
  const allTags = React.useMemo(() => collectAllTags(all), [all])
  const tagFiltered = React.useMemo(
    () => filterByTags(all, activeTags),
    [all, activeTags],
  )
  const filtered = search
    ? tagFiltered.filter((kb) => kb.name.toLowerCase().includes(search.toLowerCase()))
    : tagFiltered

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
        {allTags.length > 0 && (
          <div
            style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}
            data-testid="rag-kbs-tag-filters"
          >
            {allTags.map((t) => {
              const active = activeTags.includes(t)
              return (
                <button
                  key={t}
                  type="button"
                  className={`pill ${active ? 'pill-active' : ''}`}
                  onClick={() => setActiveTags((cur) => toggleTag(cur, t))}
                  data-testid={`rag-kbs-tag-${t}`}
                  data-active={active ? 'true' : 'false'}
                  style={{
                    fontSize: 11,
                    cursor: 'pointer',
                    background: active ? 'var(--ink)' : 'var(--bg-2, transparent)',
                    color: active ? 'var(--bg)' : 'var(--ink-2)',
                    border: '1px solid var(--line)',
                    padding: '2px 8px',
                    borderRadius: 999,
                  }}
                >
                  {t}
                </button>
              )
            })}
            {activeTags.length > 0 && (
              <button
                type="button"
                onClick={() => setActiveTags([])}
                data-testid="rag-kbs-tag-clear"
                style={{
                  fontSize: 11,
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--ink-3)',
                  cursor: 'pointer',
                }}
              >
                clear ({activeTags.length})
              </button>
            )}
          </div>
        )}
        {listQ.isPending && (
          <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>
        )}
        <table className="rag-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Tags</th>
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
                <td style={{ fontSize: 11, color: 'var(--ink-3)' }}>
                  {(kb.tags ?? []).join(', ') || '—'}
                </td>
                <td>{kb.document_count ?? '—'}</td>
                <td>{kb.chunks_count ?? '—'}</td>
                <td>{new Date(kb.created_at).toLocaleDateString()}</td>
                <td style={{ display: 'flex', gap: 8 }}>
                  <Link to="/rag/kbs/$id/overview" params={{ id: String(kb.id) }}>
                    Open
                  </Link>
                  <button
                    type="button"
                    onClick={() => {
                      setCloneTarget(kb)
                      setCloneName(`${kb.name} (copy)`)
                    }}
                    data-testid={`rag-kbs-clone-${kb.id}`}
                    style={{ fontSize: 11 }}
                  >
                    Clone
                  </button>
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
      {cloneTarget && (
        <div
          role="dialog"
          aria-label="Clone knowledge base"
          data-testid="rag-kbs-clone-dialog"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.4)',
            display: 'grid',
            placeItems: 'center',
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: 'var(--bg)',
              border: '1px solid var(--line)',
              borderRadius: 8,
              padding: 20,
              minWidth: 360,
              display: 'grid',
              gap: 12,
            }}
          >
            <h3 style={{ margin: 0 }}>Clone {cloneTarget.name}</h3>
            <label style={{ fontSize: 12, display: 'grid', gap: 4 }}>
              New name
              <input
                className="rag-input"
                value={cloneName}
                onChange={(e) => setCloneName(e.target.value)}
                data-testid="rag-kbs-clone-name"
              />
            </label>
            <label style={{ fontSize: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                type="checkbox"
                checked={cloneIncludeDocs}
                onChange={(e) => setCloneIncludeDocs(e.target.checked)}
                data-testid="rag-kbs-clone-include-docs"
              />
              Include documents (re-ingest as pending)
            </label>
            {clone.isError && (
              <p style={{ color: 'var(--err)', fontSize: 11 }}>
                {(clone.error as Error).message}
              </p>
            )}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                type="button"
                onClick={() => setCloneTarget(null)}
                disabled={clone.isPending}
                data-testid="rag-kbs-clone-cancel"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!cloneName.trim() || clone.isPending}
                onClick={() =>
                  clone.mutate({
                    srcId: cloneTarget.id,
                    name: cloneName.trim(),
                    includeDocs: cloneIncludeDocs,
                  })
                }
                data-testid="rag-kbs-clone-submit"
              >
                {clone.isPending ? 'Cloning…' : 'Clone'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
