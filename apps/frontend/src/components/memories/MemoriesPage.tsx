import { Plus, Search, Trash2 } from 'lucide-react'
import * as React from 'react'
import { PrismLogo } from '~/components/brand'
import { Dialog, DialogBody } from '~/components/ui/Dialog'

import {
  type Memory,
  useCreateMemory,
  useDeleteMemory,
  useMemoriesInfiniteQuery,
  useUpdateMemory,
} from '~/hooks/useMemoriesQuery'

type Filter = 'all' | 'system' | 'manual' | 'active' | 'paused'

const FILTERS: Filter[] = ['all', 'system', 'manual', 'active', 'paused']

function typeTone(m: Memory): 'ok' | 'warn' | 'err' | '' {
  if (!m.is_active) return 'warn'
  if (m.is_system) return 'ok'
  return ''
}

function relativeTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const diff = Date.now() - d.getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 7) return `${days}d ago`
  return d.toLocaleDateString(undefined, { month: 'short', day: '2-digit' })
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' })
}

function filterMemory(m: Memory, filter: Filter): boolean {
  switch (filter) {
    case 'all': return true
    case 'system': return m.is_system
    case 'manual': return !m.is_system
    case 'active': return m.is_active
    case 'paused': return !m.is_active
  }
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="run-main" style={{ alignItems: 'center', justifyContent: 'center', color: 'var(--ink-3)', fontSize: 13 }}>
      {label}
    </div>
  )
}

function MemoryDetail({
  m,
  onToggle,
  onDelete,
  updatePending,
}: {
  m: Memory
  onToggle: () => void
  onDelete: () => void
  updatePending: boolean
}) {
  return (
    <div className="run-main" style={{ padding: '20px 24px', gap: 16, overflowY: 'auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span className={`pill pill-${typeTone(m)}`}>
          {m.is_system ? 'system' : 'manual'}
        </span>
        <span className={`pill pill-${m.is_active ? 'ok' : 'warn'}`}>
          {m.is_active ? 'active' : 'paused'}
        </span>
        <span style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)', marginLeft: 'auto' }}>
          {m.source}
        </span>
      </div>

      <p style={{ fontSize: 13, lineHeight: 1.6, color: 'var(--ink)', margin: 0 }}>{m.content}</p>

      <table style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--ink-3)', borderCollapse: 'collapse', width: '100%' }}>
        <tbody>
          <tr>
            <td style={{ padding: '3px 12px 3px 0', fontWeight: 500, whiteSpace: 'nowrap' }}>Created</td>
            <td><time dateTime={m.created_at}>{formatDate(m.created_at)}</time></td>
          </tr>
          <tr>
            <td style={{ padding: '3px 12px 3px 0', fontWeight: 500, whiteSpace: 'nowrap' }}>Updated</td>
            <td><time dateTime={m.updated_at}>{formatDate(m.updated_at)}</time></td>
          </tr>
          {m.is_system && (
            <tr>
              <td style={{ padding: '3px 12px 3px 0', fontWeight: 500, whiteSpace: 'nowrap' }}>Note</td>
              <td>Auto-maintained from conversations</td>
            </tr>
          )}
        </tbody>
      </table>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
        <button
          type="button"
          className="btn btn-sm"
          disabled={updatePending}
          onClick={onToggle}
        >
          {m.is_active ? 'Pause' : 'Resume'}
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          style={{ marginLeft: 'auto', color: 'var(--err)' }}
          onClick={onDelete}
          title="Delete memory"
        >
          <Trash2 style={{ width: 11, height: 11 }} aria-hidden /> forget
        </button>
      </div>
    </div>
  )
}

export function MemoriesPage() {
  const memoriesQ = useMemoriesInfiniteQuery(25)
  const createMut = useCreateMemory()
  const updateMut = useUpdateMemory()
  const deleteMut = useDeleteMemory()

  const [draft, setDraft] = React.useState('')
  const [search, setSearch] = React.useState('')
  const [filter, setFilter] = React.useState<Filter>('all')
  const [selected, setSelected] = React.useState<Memory | null>(null)
  const [pendingDelete, setPendingDelete] = React.useState<{ id: number; content: string } | null>(null)

  const loadMoreRef = React.useRef<HTMLDivElement | null>(null)
  const listScrollRef = React.useRef<HTMLDivElement | null>(null)

  const memories = React.useMemo(
    () => memoriesQ.data?.pages.flatMap((p) => p.items) ?? [],
    [memoriesQ.data],
  )

  const searchedMemories = React.useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return memories
    return memories.filter((m) =>
      [m.content, m.source, m.is_active ? 'active' : 'paused', m.is_system ? 'system' : 'manual']
        .join(' ')
        .toLowerCase()
        .includes(q),
    )
  }, [memories, search])

  const filtered = React.useMemo(
    () =>
      [...searchedMemories]
        .filter((m) => filterMemory(m, filter))
        .sort((a, b) => Number(b.is_system) - Number(a.is_system) || b.id - a.id),
    [searchedMemories, filter],
  )

  // Keep selected in sync when data refreshes
  React.useEffect(() => {
    if (selected) {
      const fresh = memories.find((m) => m.id === selected.id)
      if (fresh) setSelected(fresh)
    }
  }, [memories]) // eslint-disable-line react-hooks/exhaustive-deps

  React.useEffect(() => {
    const el = loadMoreRef.current
    if (!el) return
    const obs = new IntersectionObserver(
      (entries) => {
        if (
          entries.some((e) => e.isIntersecting) &&
          memoriesQ.hasNextPage &&
          !memoriesQ.isFetchingNextPage
        ) {
          void memoriesQ.fetchNextPage()
        }
      },
      { root: listScrollRef.current, rootMargin: '200px' },
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [memoriesQ])

  const handleCreate = () => {
    const text = draft.trim()
    if (!text) return
    createMut.mutate(text, { onSuccess: () => setDraft('') })
  }

  return (
    <>
      {/* Header */}
      <div style={{ padding: '16px 20px 0', borderBottom: '1px solid var(--line)', background: 'var(--panel)', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
          <div>
            <h1 style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)', margin: 0 }}>Memories</h1>
            <p style={{ fontSize: 11, color: 'var(--ink-3)', margin: '2px 0 0' }}>
              Long-term facts included in every conversation.
            </p>
          </div>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={!draft.trim() || createMut.isPending}
            onClick={handleCreate}
            style={{ display: 'none' }}
          >
            <Plus style={{ width: 12, height: 12 }} aria-hidden /> add
          </button>
        </div>

        {/* Add memory row */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <input
            style={{ flex: 1, fontSize: 12, background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 4, padding: '4px 8px', color: 'var(--ink)', outline: 'none', fontFamily: 'inherit' }}
            placeholder="e.g. I prefer TypeScript over JavaScript"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleCreate()
              }
            }}
            maxLength={2000}
            disabled={createMut.isPending}
          />
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={!draft.trim() || createMut.isPending}
            onClick={handleCreate}
          >
            <Plus style={{ width: 12, height: 12 }} aria-hidden /> Add
          </button>
        </div>
        {createMut.isError && (
          <p style={{ fontSize: 11, color: 'var(--err)', marginTop: -8, marginBottom: 8 }}>
            {(createMut.error as Error).message}
          </p>
        )}
      </div>

      {/* Main grid */}
      <div className="run-grid" data-testid="memories-page" style={{ flex: 1, minHeight: 0 }}>
        {/* Left: list */}
        <div className="run-list" ref={listScrollRef}>
          {/* Search */}
          <div style={{ padding: '10px 12px 6px', borderBottom: '1px solid var(--line)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 6, padding: '5px 10px' }}>
              <Search style={{ width: 12, height: 12, color: 'var(--ink-3)', flexShrink: 0 }} aria-hidden />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search memories..."
                style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', fontSize: 11, color: 'var(--ink)', fontFamily: 'inherit' }}
                aria-label="Search memories"
              />
            </div>
          </div>

          {/* Filter chips */}
          <div className="filter-bar" style={{ padding: '8px 12px', borderBottom: '1px solid var(--line)' }}>
            {FILTERS.map((t) => (
              <button
                key={t}
                className={`filter-chip ${filter === t ? 'active' : ''}`}
                onClick={() => setFilter(t)}
              >
                {t}
              </button>
            ))}
          </div>

          {/* List items */}
          {memoriesQ.isPending && (
            <div style={{ padding: 20, display: 'flex', justifyContent: 'center' }}>
              <PrismLogo state="loading" size={20} />
            </div>
          )}
          {memoriesQ.isError && (
            <p style={{ padding: '12px 14px', fontSize: 12, color: 'var(--err)' }}>
              {(memoriesQ.error as Error).message}
            </p>
          )}
          {!memoriesQ.isPending && memories.length === 0 && (
            <p style={{ padding: '12px 14px', fontSize: 12, color: 'var(--ink-3)' }}>
              No memories yet. Add one above or start chatting.
            </p>
          )}
          {!memoriesQ.isPending && memories.length > 0 && filtered.length === 0 && (
            <p style={{ padding: '12px 14px', fontSize: 12, color: 'var(--ink-3)' }}>
              No memories match your filter.
            </p>
          )}
          {filtered.map((m) => (
            <div
              key={m.id}
              className={`run-list-item ${selected?.id === m.id ? 'active' : ''}`}
              onClick={() => setSelected(m)}
            >
              <div className="title" style={{ opacity: m.is_active ? 1 : 0.6 }}>
                {m.content.length > 90 ? m.content.slice(0, 90) + '…' : m.content}
              </div>
              <div className="meta mono">
                <span className={`pill pill-${typeTone(m)}`}>
                  {m.is_system ? 'system' : 'manual'}
                </span>
                <span>{relativeTime(m.updated_at)}</span>
                {!m.is_active && <span style={{ color: 'var(--warn)' }}>paused</span>}
              </div>
            </div>
          ))}
          <div ref={loadMoreRef} style={{ height: 4 }} />
          {memoriesQ.isFetchingNextPage && (
            <p style={{ padding: '8px 14px', fontSize: 11, color: 'var(--ink-3)' }}>Loading more…</p>
          )}
        </div>

        {/* Right: detail panel */}
        {selected ? (
          <MemoryDetail
            m={selected}
            onToggle={() => updateMut.mutate({ id: selected.id, is_active: !selected.is_active })}
            onDelete={() => setPendingDelete({ id: selected.id, content: selected.content })}
            updatePending={updateMut.isPending}
          />
        ) : (
          <EmptyState label="Pick a memory to inspect." />
        )}
      </div>

      <Dialog
        open={pendingDelete != null}
        onClose={() => setPendingDelete(null)}
        title="Delete memory?"
        size="sm"
        footer={
          <>
            <button type="button" className="btn btn-sm" onClick={() => setPendingDelete(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-sm"
              style={{ color: 'var(--err)' }}
              disabled={deleteMut.isPending}
              onClick={() => {
                if (!pendingDelete) return
                deleteMut.mutate(pendingDelete.id, {
                  onSuccess: () => {
                    setPendingDelete(null)
                    setSelected((prev) => (prev?.id === pendingDelete.id ? null : prev))
                  },
                })
              }}
            >
              Delete
            </button>
          </>
        }
      >
        <DialogBody>
          <p className="text-sm" style={{ color: 'var(--ink-2)' }}>
            This action cannot be undone.
          </p>
          {pendingDelete && (
            <p
              className="mt-2 line-clamp-2 rounded-md px-2 py-1 text-xs"
              style={{
                border: '1px solid var(--line)',
                background: 'var(--bg-2)',
                color: 'var(--ink-2)',
              }}
            >
              {pendingDelete.content}
            </p>
          )}
        </DialogBody>
      </Dialog>
    </>
  )
}
