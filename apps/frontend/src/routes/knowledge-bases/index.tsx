import { useInfiniteQuery } from '@tanstack/react-query'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { Plus, Search } from 'lucide-react'
import * as React from 'react'
import { PrismLogo } from '~/components/brand'

import { CreateKnowledgeBaseDialog } from '~/components/knowledge-bases/CreateKnowledgeBaseDialog'
import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import type { KnowledgeBaseSummary } from '~/lib/knowledge-base-types'
import { queryKeys } from '~/lib/queryKeys'

export const Route = createFileRoute('/knowledge-bases/')({
  component: KnowledgeBasesIndexPage,
})

function relativeTime(iso: string) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const diff = Date.now() - d.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 30) return `${days}d ago`
  return d.toLocaleDateString(undefined, { month: 'short', day: '2-digit', year: 'numeric' })
}

function KnowledgeBasesIndexPage() {
  const apiBase = getApiBase()
  const navigate = useNavigate()
  const [createOpen, setCreateOpen] = React.useState(false)
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
    getNextPageParam: (lastPage) => lastPage.next_cursor,
  })

  const rows = React.useMemo(
    () => listQ.data?.pages.flatMap((p) => p.items) ?? [],
    [listQ.data],
  )

  const filteredRows = React.useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((kb) => {
      const name = kb.name.toLowerCase()
      const desc = (kb.description ?? '').toLowerCase()
      return name.includes(q) || desc.includes(q)
    })
  }, [rows, search])

  const loadMoreRef = React.useRef<HTMLDivElement | null>(null)

  React.useEffect(() => {
    const el = loadMoreRef.current
    if (!el) return
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting) && listQ.hasNextPage && !listQ.isFetchingNextPage) {
          void listQ.fetchNextPage()
        }
      },
      { rootMargin: '200px' },
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [listQ])

  // Derive stats locally from loaded rows
  const totalDocs = rows.reduce((acc, kb) => acc + (kb.document_count ?? 0), 0)

  return (
    <div className="main-inner">
      <header className="screen-head">
        <div>
          <h1>Knowledge bases</h1>
          <div className="kpi-row" style={{ border: 0, background: 'transparent', paddingTop: 8, paddingLeft: 0, paddingRight: 0, paddingBottom: 0 }}>
            <div className="kpi" style={{ padding: '8px 16px 0 0', border: 0 }}>
              <div className="kpi-label">KBs</div>
              <div className="kpi-value" style={{ fontSize: 16 }}>{rows.length}</div>
            </div>
            <div className="kpi" style={{ padding: '8px 16px 0 0', border: 0 }}>
              <div className="kpi-label">Documents</div>
              <div className="kpi-value" style={{ fontSize: 16 }}>{totalDocs.toLocaleString()}</div>
            </div>
            <div className="kpi" style={{ padding: '8px 0 0 0', border: 0 }}>
              <div className="kpi-label">Retrievals · 7d</div>
              <div className="kpi-value" style={{ fontSize: 16 }}>—</div>
            </div>
          </div>
        </div>
        <div className="right">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => setCreateOpen(true)}
          >
            <Plus style={{ width: 12, height: 12 }} aria-hidden />
            Add knowledge base
          </button>
        </div>
      </header>

      <div style={{ padding: '10px 24px', borderBottom: '1px solid var(--line)', background: 'var(--bg)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 4, padding: '0 10px', height: 32 }}>
          <Search style={{ width: 14, height: 14, color: 'var(--ink-3)', flexShrink: 0 }} aria-hidden />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search knowledge bases..."
            aria-label="Search knowledge bases"
            style={{ flex: 1, background: 'transparent', border: 0, outline: 'none', fontSize: 12, color: 'var(--ink)', minWidth: 0 }}
          />
        </div>
      </div>

      <CreateKnowledgeBaseDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(kb) => {
          void navigate({
            to: '/knowledge-bases/$id',
            params: { id: String(kb.id) },
          })
        }}
      />

      {listQ.isPending && <PrismLogo state="loading" size={20} className="my-4 mx-auto" />}
      {listQ.isError && (
        <p style={{ padding: '16px 24px', fontSize: 13, color: 'var(--err)' }} role="alert">
          {(listQ.error as Error).message}
        </p>
      )}
      {!listQ.isPending && rows.length === 0 && (
        <p style={{ padding: '16px 24px', fontSize: 13, color: 'var(--ink-3)' }}>
          None yet — use <strong>Add knowledge base</strong>.
        </p>
      )}
      {!listQ.isPending && rows.length > 0 && filteredRows.length === 0 && (
        <p style={{ padding: '16px 24px', fontSize: 13, color: 'var(--ink-3)' }}>
          No knowledge bases match your search.
        </p>
      )}

      {filteredRows.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="tbl" data-testid="kb-list">
            <thead>
              <tr>
                <th>Name</th>
                <th>Docs</th>
                <th>Created</th>
                <th style={{ textAlign: 'right' }}>Size</th>
                <th style={{ textAlign: 'right' }}>Chunks</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((kb) => (
                <tr
                  key={kb.id}
                  onClick={() => void navigate({ to: '/knowledge-bases/$id', params: { id: String(kb.id) } })}
                >
                  <td className="name-cell">
                    {kb.name}
                    {kb.description ? (
                      <div className="sub">{kb.description}</div>
                    ) : null}
                  </td>
                  <td className="num">{(kb.document_count ?? 0).toLocaleString()}</td>
                  <td className="muted">{relativeTime(kb.created_at)}</td>
                  <td className="num">{formatBytes(kb.size_bytes)}</td>
                  <td className="num">{(kb.chunks_count ?? 0).toLocaleString()}</td>
                  <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                    <a
                      href={`/knowledge-bases/${kb.id}`}
                      title="View knowledge base"
                      aria-label={`View ${kb.name}`}
                      style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 26, height: 26, borderRadius: 3, border: '1px solid var(--line)', color: 'var(--ink-2)', textDecoration: 'none' }}
                      onClick={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        void navigate({ to: '/knowledge-bases/$id', params: { id: String(kb.id) } })
                      }}
                    >
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                        <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
                        <circle cx="12" cy="12" r="3"/>
                      </svg>
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div ref={loadMoreRef} style={{ height: 1 }} />
          {listQ.isFetchingNextPage && (
            <p style={{ padding: '8px 24px', fontSize: 12, color: 'var(--ink-3)' }}>Loading more…</p>
          )}
        </div>
      )}
    </div>
  )
}

function formatBytes(bytes: number | undefined) {
  if (bytes == null) return '—'
  if (bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i += 1
  }
  return `${value.toFixed(value >= 10 || i === 0 ? 0 : 1)} ${units[i]}`
}
