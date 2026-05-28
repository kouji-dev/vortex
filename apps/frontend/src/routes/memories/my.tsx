/**
 * /memories/my — "My memories" page.
 *
 * Wraps the legacy `MemoriesPage` (single auto-profile row + manual rows from
 * `/api/users/me/memories`) and layers a v1-style toolbar on top showing the
 * pluggable v1 memory list with filter/edit/delete/pin/star/importance.
 */
import { createFileRoute } from '@tanstack/react-router'
import { Pin, Search, Star, Trash2 } from 'lucide-react'
import * as React from 'react'

import {
  useBulkDeleteMemoriesV1,
  useBulkPinMemoriesV1,
  useBulkTagMemoriesV1,
  useDeleteMemoryV1,
  useMemoriesV1Query,
  usePatchMemoryV1,
} from '~/hooks/useMemoriesV1Query'
import {
  MEMORY_TYPES,
  SCOPE_KINDS,
  countByType,
  filterMemories,
  quantizeImportance,
  type MemoryType,
  type MemoryV1,
  type ScopeKind,
} from '~/lib/memories-types'

export const Route = createFileRoute('/memories/my')({
  component: MyMemoriesPage,
})

function MyMemoriesPage() {
  const [type, setType] = React.useState<MemoryType | 'all'>('all')
  const [scope, setScope] = React.useState<ScopeKind | 'all'>('all')
  const [q, setQ] = React.useState('')
  const [selected, setSelected] = React.useState<Set<string>>(new Set())

  const list = useMemoriesV1Query({
    type: type === 'all' ? undefined : type,
    scope: scope === 'all' ? undefined : scope,
    q: q || undefined,
  })

  const patch = usePatchMemoryV1()
  const del = useDeleteMemoryV1()
  const bulk = useBulkDeleteMemoriesV1()
  const bulkPin = useBulkPinMemoriesV1()
  const bulkTag = useBulkTagMemoriesV1()

  const memories = list.data ?? []
  const filtered = React.useMemo(
    () => filterMemories(memories, { type, scope, q }),
    [memories, type, scope, q],
  )
  const counts = countByType(memories)

  function toggleSelected(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function selectAll() {
    setSelected(new Set(filtered.map((m) => m.id)))
  }

  function clearSelection() {
    setSelected(new Set())
  }

  function pin(m: MemoryV1) {
    patch.mutate({ id: m.id, body: { pinned: !m.pinned } })
  }

  function setImportance(m: MemoryV1, v: number) {
    patch.mutate({ id: m.id, body: { importance: quantizeImportance(v) } })
  }

  function bulkDelete() {
    if (selected.size === 0) return
    bulk.mutate(
      { ids: Array.from(selected) },
      { onSuccess: () => clearSelection() },
    )
  }

  function bulkPinSet(pinned: boolean) {
    if (selected.size === 0) return
    bulkPin.mutate({ ids: Array.from(selected), pinned })
  }

  function bulkTagPrompt(mode: 'add' | 'remove') {
    if (selected.size === 0) return
    const raw = window.prompt(
      mode === 'add' ? 'Tags to add (comma-separated):' : 'Tags to remove (comma-separated):',
      '',
    )
    if (!raw) return
    const tags = raw.split(',').map((t) => t.trim()).filter(Boolean)
    if (!tags.length) return
    bulkTag.mutate({
      ids: Array.from(selected),
      add: mode === 'add' ? tags : [],
      remove: mode === 'remove' ? tags : [],
    })
  }

  return (
    <div data-testid="memories-my" style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 16, flex: 1, minHeight: 0 }}>
      {/* Toolbar */}
      <div className="panel">
        <div className="panel-head" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>My memories</span>
          <span className="meta">{filtered.length} of {memories.length}</span>
        </div>
        <div style={{ padding: 12, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 4, padding: '4px 8px', flex: '1 1 200px' }}>
            <Search style={{ width: 12, height: 12, color: 'var(--ink-3)' }} aria-hidden />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search text…"
              style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', fontSize: 12, color: 'var(--ink)' }}
              data-testid="mem-my-search"
            />
          </div>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as MemoryType | 'all')}
            data-testid="mem-my-type"
            style={selectStyle}
          >
            <option value="all">all types</option>
            {MEMORY_TYPES.map((t) => (
              <option key={t} value={t}>{t} ({counts[t]})</option>
            ))}
          </select>
          <select
            value={scope}
            onChange={(e) => setScope(e.target.value as ScopeKind | 'all')}
            data-testid="mem-my-scope"
            style={selectStyle}
          >
            <option value="all">all scopes</option>
            {SCOPE_KINDS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          {selected.size > 0 && (
            <>
              <span className="meta" data-testid="mem-my-selected-count">{selected.size} selected</span>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => bulkPinSet(true)}
                disabled={bulkPin.isPending}
                data-testid="mem-my-bulk-pin"
                title="Pin selected"
              >
                <Pin style={{ width: 11, height: 11 }} aria-hidden /> Pin
              </button>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => bulkPinSet(false)}
                disabled={bulkPin.isPending}
                data-testid="mem-my-bulk-unpin"
                title="Unpin selected"
              >
                Unpin
              </button>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => bulkTagPrompt('add')}
                disabled={bulkTag.isPending}
                data-testid="mem-my-bulk-tag-add"
                title="Add tags to selection"
              >
                Tag +
              </button>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => bulkTagPrompt('remove')}
                disabled={bulkTag.isPending}
                data-testid="mem-my-bulk-tag-remove"
                title="Remove tags from selection"
              >
                Tag −
              </button>
              <button
                type="button"
                className="btn btn-sm"
                onClick={bulkDelete}
                disabled={bulk.isPending}
                style={{ color: 'var(--err)' }}
                data-testid="mem-my-bulk-delete"
              >
                <Trash2 style={{ width: 11, height: 11 }} aria-hidden /> Delete {selected.size}
              </button>
              <button type="button" className="btn btn-sm" onClick={clearSelection}>Clear</button>
            </>
          )}
          {selected.size === 0 && filtered.length > 0 && (
            <button type="button" className="btn btn-sm" onClick={selectAll} data-testid="mem-my-select-all">
              Select all
            </button>
          )}
        </div>
      </div>

      {/* List */}
      <div className="panel" style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        {list.isPending && (
          <p style={{ padding: 12, fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>
        )}
        {list.isError && (
          <p style={{ padding: 12, fontSize: 12, color: 'var(--err)' }}>{(list.error as Error).message}</p>
        )}
        {list.isSuccess && filtered.length === 0 && (
          <p style={{ padding: 12, fontSize: 12, color: 'var(--ink-3)' }}>No memories match.</p>
        )}
        {filtered.map((m) => {
          const isSel = selected.has(m.id)
          return (
            <div
              key={m.id}
              data-testid="mem-my-row"
              data-memory-id={m.id}
              style={{
                display: 'grid',
                gridTemplateColumns: '24px 90px 90px 1fr 120px 100px',
                gap: 8,
                alignItems: 'center',
                padding: '8px 12px',
                borderBottom: '1px solid var(--line)',
                background: isSel ? 'var(--bg-2)' : undefined,
              }}
            >
              <input
                type="checkbox"
                checked={isSel}
                onChange={() => toggleSelected(m.id)}
                aria-label={`select ${m.id}`}
              />
              <span className="pill" style={{ fontSize: 10 }}>{m.type}</span>
              <span className="pill" style={{ fontSize: 10 }}>{m.scope_kind}</span>
              <EditableText
                value={m.text}
                onSave={(v) => patch.mutate({ id: m.id, body: { text: v } })}
                disabled={patch.isPending}
              />
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={m.importance}
                onChange={(e) => setImportance(m, Number(e.target.value))}
                aria-label={`importance for ${m.id}`}
                data-testid="mem-my-importance"
                style={{ width: '100%' }}
              />
              <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  className="btn btn-xs"
                  onClick={() => pin(m)}
                  title={m.pinned ? 'Unpin' : 'Pin'}
                  data-testid="mem-my-pin"
                  style={{ color: m.pinned ? 'var(--accent)' : undefined }}
                >
                  {m.pinned ? <Star style={{ width: 11, height: 11 }} /> : <Pin style={{ width: 11, height: 11 }} />}
                </button>
                <button
                  type="button"
                  className="btn btn-xs"
                  style={{ color: 'var(--err)' }}
                  onClick={() => del.mutate(m.id)}
                  title="Delete"
                  data-testid="mem-my-delete"
                >
                  <Trash2 style={{ width: 11, height: 11 }} />
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function EditableText({
  value,
  onSave,
  disabled,
}: {
  value: string
  onSave: (v: string) => void
  disabled?: boolean
}) {
  const [editing, setEditing] = React.useState(false)
  const [draft, setDraft] = React.useState(value)

  React.useEffect(() => {
    if (!editing) setDraft(value)
  }, [value, editing])

  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => setEditing(true)}
        style={{
          textAlign: 'left',
          fontSize: 12,
          color: 'var(--ink)',
          background: 'transparent',
          border: 'none',
          padding: 0,
          cursor: 'text',
          font: 'inherit',
        }}
        data-testid="mem-my-text"
      >
        {value}
      </button>
    )
  }
  return (
    <input
      autoFocus
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        if (draft !== value) onSave(draft)
        setEditing(false)
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
        if (e.key === 'Escape') {
          setDraft(value)
          setEditing(false)
        }
      }}
      disabled={disabled}
      style={{
        fontSize: 12,
        background: 'var(--bg)',
        border: '1px solid var(--line)',
        borderRadius: 4,
        padding: '4px 6px',
        color: 'var(--ink)',
        outline: 'none',
        width: '100%',
      }}
      data-testid="mem-my-text-input"
    />
  )
}

const selectStyle: React.CSSProperties = {
  borderRadius: 4,
  border: '1px solid var(--line)',
  background: 'var(--bg)',
  color: 'var(--ink)',
  padding: '4px 8px',
  fontSize: 12,
}
