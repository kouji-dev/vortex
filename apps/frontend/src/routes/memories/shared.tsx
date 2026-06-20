/**
 * /memories/shared — team / org / assistant scoped memories.
 *
 * Read-only for non-admin users. The admin edit affordance is gated server-side
 * via `memory:admin`. Here we still render the same patch/delete buttons but
 * they will simply 403; we show a hint in the toolbar.
 */
import { Select } from '~/components/ui/select'
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'

import { useMeQuery } from '~/hooks/useMeQuery'
import { useDeleteMemoryV1, useMemoriesV1Query, usePatchMemoryV1 } from '~/hooks/useMemoriesV1Query'
import { isAdminActor } from '~/lib/admin-permissions'
import {
  MEMORY_TYPES,
  SHARED_SCOPES,
  filterMemories,
  isShared,
  type MemorySource,
  type MemoryType,
  type MemoryV1,
  type ScopeKind,
} from '~/lib/memories-types'

export const Route = createFileRoute('/memories/shared')({
  component: SharedMemoriesPage,
})

function SharedMemoriesPage() {
  const me = useMeQuery()
  const list = useMemoriesV1Query({ limit: 500 })
  const patch = usePatchMemoryV1()
  const del = useDeleteMemoryV1()

  const [scope, setScope] = React.useState<ScopeKind | 'all'>('all')
  const [type, setType] = React.useState<MemoryType | 'all'>('all')
  const [source, setSource] = React.useState<MemorySource>('all')
  const isAdmin = me.isSuccess && isAdminActor(me.data?.roles)

  const sharedOnly = React.useMemo(() => (list.data ?? []).filter(isShared), [list.data])
  const filtered = React.useMemo(
    () => filterMemories(sharedOnly, { scope, type, source }),
    [sharedOnly, scope, type, source],
  )

  return (
    <div data-testid="memories-shared" style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 16, flex: 1, minHeight: 0 }}>
      <div className="panel">
        <div className="panel-head" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>Shared memories</span>
          <span className="meta">
            {isAdmin ? 'Admin edit enabled' : 'Read-only'} · {filtered.length} shown
          </span>
        </div>
        <div style={{ padding: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Select
            value={scope}
            onChange={(e) => setScope(e.target.value as ScopeKind | 'all')}
            data-testid="mem-shared-scope"
            style={selectStyle}
          size="sm"
          inline
          >
            <option value="all">all (team + org + assistant)</option>
            {SHARED_SCOPES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </Select>
          <Select
            value={type}
            onChange={(e) => setType(e.target.value as MemoryType | 'all')}
            data-testid="mem-shared-type"
            style={selectStyle}
          size="sm"
          inline
          >
            <option value="all">all types</option>
            {MEMORY_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </Select>
          <Select
            value={source}
            onChange={(e) => setSource(e.target.value as MemorySource)}
            data-testid="mem-shared-source"
            style={selectStyle}
          size="sm"
          inline
          >
            <option value="all">all sources</option>
            <option value="auto">auto (extracted)</option>
            <option value="manual">manual</option>
          </Select>
        </div>
      </div>

      <div className="panel" style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        {list.isPending && (
          <p style={{ padding: 12, fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>
        )}
        {list.isError && (
          <p style={{ padding: 12, fontSize: 12, color: 'var(--err)' }}>{(list.error as Error).message}</p>
        )}
        {list.isSuccess && filtered.length === 0 && (
          <p style={{ padding: 12, fontSize: 12, color: 'var(--ink-3)' }}>No shared memories.</p>
        )}
        {filtered.map((m) => (
          <SharedRow
            key={m.id}
            m={m}
            canEdit={isAdmin}
            onPatch={(text) => patch.mutate({ id: m.id, body: { text } })}
            onDelete={() => del.mutate(m.id)}
            disabled={patch.isPending || del.isPending}
          />
        ))}
      </div>
    </div>
  )
}

function SharedRow({
  m,
  canEdit,
  onPatch,
  onDelete,
  disabled,
}: {
  m: MemoryV1
  canEdit: boolean
  onPatch: (text: string) => void
  onDelete: () => void
  disabled?: boolean
}) {
  const [editing, setEditing] = React.useState(false)
  const [draft, setDraft] = React.useState(m.text)
  React.useEffect(() => {
    if (!editing) setDraft(m.text)
  }, [m.text, editing])

  return (
    <div
      data-testid="mem-shared-row"
      data-memory-id={m.id}
      style={{
        display: 'grid',
        gridTemplateColumns: '90px 90px 1fr 120px',
        gap: 8,
        alignItems: 'center',
        padding: '8px 12px',
        borderBottom: '1px solid var(--line)',
      }}
    >
      <span className="pill" style={{ fontSize: 10 }}>{m.scope_kind}</span>
      <span className="pill" style={{ fontSize: 10 }}>{m.type}</span>
      {canEdit && editing ? (
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => {
            if (draft !== m.text) onPatch(draft)
            setEditing(false)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
          }}
          disabled={disabled}
          style={inputStyle}
        />
      ) : (
        <button
          type="button"
          onClick={() => canEdit && setEditing(true)}
          disabled={!canEdit}
          style={{
            textAlign: 'left',
            fontSize: 12,
            color: 'var(--ink)',
            background: 'transparent',
            border: 'none',
            padding: 0,
            cursor: canEdit ? 'text' : 'default',
            font: 'inherit',
          }}
        >
          {m.text}
        </button>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        {canEdit && (
          <button
            type="button"
            className="btn btn-xs"
            style={{ color: 'var(--err)' }}
            onClick={onDelete}
            disabled={disabled}
            data-testid="mem-shared-delete"
          >
            Delete
          </button>
        )}
      </div>
    </div>
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

const inputStyle: React.CSSProperties = {
  fontSize: 12,
  background: 'var(--bg)',
  border: '1px solid var(--line)',
  borderRadius: 4,
  padding: '4px 6px',
  color: 'var(--ink)',
  outline: 'none',
  width: '100%',
}
