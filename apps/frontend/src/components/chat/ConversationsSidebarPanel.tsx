import { Link, useLocation, useNavigate } from '@tanstack/react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Library, Plus, Search, Trash2 } from 'lucide-react'
import * as React from 'react'
import { PrismLogo } from '~/components/brand'
import {
  ProviderMark,
} from '~/components/chat/ChatComposerDock'

import {
  catalogModelByStoredModel,
  useCatalogModelsQuery,
} from '~/hooks/useCatalogModelsQuery'
import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import type { Conversation } from '~/lib/chat-types'
import { queryKeys } from '~/lib/queryKeys'

type ConversationsSidebarPanelProps = {
  conversations: Conversation[] | undefined
  conversationsPending: boolean
  conversationsError: Error | null
  onNewConversation: () => void
  hideHeader?: boolean
  onSelectConversation?: () => void
}

function groupByRecency(convs: Conversation[]) {
  const today: Conversation[] = []
  const yesterday: Conversation[] = []
  const earlier: Conversation[] = []
  const now = Date.now()
  for (const c of convs) {
    const days = (now - new Date(c.created_at).getTime()) / (1000 * 60 * 60 * 24)
    if (days < 1) today.push(c)
    else if (days < 2) yesterday.push(c)
    else earlier.push(c)
  }
  return { today, yesterday, earlier }
}

function formatWhenShort(iso: string): string {
  try {
    const d = new Date(iso).getTime()
    if (Number.isNaN(d)) return ''
    const diffSec = Math.max(0, (Date.now() - d) / 1000)
    if (diffSec < 60) return 'just now'
    const min = diffSec / 60
    if (min < 60) return `${Math.round(min)}m ago`
    const hr = min / 60
    if (hr < 24) return `${Math.round(hr)}h ago`
    const day = hr / 24
    if (day < 7) return `${Math.round(day)}d ago`
    const wk = day / 7
    if (wk < 5) return `${Math.round(wk)}w ago`
    const mo = day / 30
    if (mo < 12) return `${Math.round(mo)}mo ago`
    return `${Math.round(day / 365)}y ago`
  } catch { return '' }
}

export function ConversationsSidebarPanel({
  conversations,
  conversationsPending,
  conversationsError,
  onNewConversation,
  hideHeader,
  onSelectConversation,
}: ConversationsSidebarPanelProps) {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const catalogModels = useCatalogModelsQuery()
  const [searchQuery, setSearchQuery] = React.useState('')
  const activeConvId = React.useMemo(() => {
    const m = location.pathname.match(/\/chat\/conversations\/(\d+)/)
    return m ? Number(m[1]) : null
  }, [location.pathname])
  const [selectionMode, setSelectionMode] = React.useState(false)
  const [selectedIds, setSelectedIds] = React.useState<Set<number>>(new Set())
  const [confirmDelete, setConfirmDelete] = React.useState<
    | { kind: 'single'; id: number; label: string }
    | { kind: 'bulk'; ids: number[] }
    | null
  >(null)
  const selectAllRef = React.useRef<HTMLInputElement | null>(null)
  const conversationIds = React.useMemo(() => (conversations ?? []).map((c) => c.id), [conversations])

  const toggleSelected = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const singleDeleteMut = useMutation({
    mutationFn: async (conversationId: number) => {
      const res = await fetch(`${apiBase}/api/chat/conversations/${conversationId}`, {
        method: 'DELETE',
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(await res.text())
    },
    onSuccess: (_, deletedId) => {
      setConfirmDelete(null)
      void qc.invalidateQueries({ queryKey: queryKeys.conversations() })
      if (deletedId === activeConvId) {
        void navigate({ to: '/chat/conversations' })
      }
    },
  })

  const bulkDeleteMut = useMutation({
    mutationFn: async (ids: number[]) => {
      await Promise.all(
        ids.map(async (conversationId) => {
          const res = await fetch(`${apiBase}/api/chat/conversations/${conversationId}`, {
            method: 'DELETE',
            headers: await getAuthHeaders(),
          })
          if (!res.ok) throw new Error(await res.text())
        }),
      )
    },
    onSuccess: (_, deletedIds) => {
      setConfirmDelete(null)
      setSelectedIds(new Set())
      setSelectionMode(false)
      void qc.invalidateQueries({ queryKey: queryKeys.conversations() })
      if (activeConvId != null && deletedIds.includes(activeConvId)) {
        void navigate({ to: '/chat/conversations' })
      }
    },
  })

  const selectedCount = selectedIds.size
  const allSelected = conversationIds.length > 0 && conversationIds.every((id) => selectedIds.has(id))
  const someSelected = selectedCount > 0 && !allSelected

  React.useEffect(() => {
    if (!selectionMode) return
    setSelectedIds((prev) => {
      const valid = new Set(conversationIds)
      const next = new Set<number>()
      prev.forEach((id) => {
        if (valid.has(id)) next.add(id)
      })
      return next.size === prev.size ? prev : next
    })
  }, [conversationIds, selectionMode])

  React.useEffect(() => {
    if (!selectAllRef.current) return
    selectAllRef.current.indeterminate = someSelected
  }, [someSelected, selectedCount])

  const filteredConvs = React.useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return conversations ?? []
    return (conversations ?? []).filter((c) =>
      (c.title ?? '').toLowerCase().includes(q),
    )
  }, [conversations, searchQuery])

  const groups = React.useMemo(() => groupByRecency(filteredConvs), [filteredConvs])

  function renderConvRow(c: Conversation) {
    const isActive = c.id === activeConvId
    const catalogRow = c.model
      ? catalogModelByStoredModel(catalogModels.data, c.model)
      : undefined
    const kbCount = c.knowledge_base_ids?.length ?? 0
    return (
      <div
        key={c.id}
        className={`conv-row group ${isActive ? 'active' : ''}`}
        data-testid={`chat-conv-row-${c.id}`}
        style={{ position: 'relative' }}
      >
        {selectionMode && (
          <label
            className="inline-flex shrink-0 items-center"
            style={{ position: 'absolute', top: 10, left: 12, zIndex: 1 }}
          >
            <input
              type="checkbox"
              className="size-3.5 rounded"
              checked={selectedIds.has(c.id)}
              onChange={() => toggleSelected(c.id)}
              aria-label={`Select conversation ${c.title ?? c.id}`}
            />
          </label>
        )}
        <Link
          to="/chat/conversations/$id"
          params={{ id: String(c.id) }}
          className="block"
          onClick={onSelectConversation}
          style={{ paddingLeft: selectionMode ? 22 : 0 }}
        >
          <div className="top">
            <span className="title">{c.title ?? 'New conversation'}</span>
            <span className="when">{formatWhenShort(c.created_at)}</span>
          </div>
          {(catalogRow || kbCount > 0) && (
            <div className="meta">
              {catalogRow && (
                <>
                  <ProviderMark model={catalogRow} />
                  <span className="mono muted">{catalogRow.display_name}</span>
                </>
              )}
              {catalogRow && kbCount > 0 && <span className="sep">·</span>}
              {kbCount > 0 && (
                <span className="cap-tag">
                  <Library className="size-3" strokeWidth={2} aria-hidden />
                  {kbCount} KB
                </span>
              )}
            </div>
          )}
        </Link>
        {!selectionMode && (
          <button
            type="button"
            className="inline-flex items-center justify-center rounded opacity-0 transition group-hover:opacity-100"
            title="Delete conversation"
            aria-label="Delete conversation"
            style={{
              position: 'absolute',
              bottom: 6,
              right: 6,
              width: 20,
              height: 20,
              color: 'var(--ink-3)',
            }}
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              setConfirmDelete({
                kind: 'single',
                id: c.id,
                label: c.title?.trim() || `Conversation #${c.id}`,
              })
            }}
          >
            <Trash2 className="size-3" aria-hidden />
            <span className="sr-only">Delete</span>
          </button>
        )}
      </div>
    )
  }

  return (
    <aside className="conv-list">
      {!hideHeader && (
        <div className="conv-list-head">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            style={{ width: '100%' }}
            onClick={onNewConversation}
            data-testid="sidebar-new-conversation"
          >
            <Plus className="size-3" aria-hidden />
            New conversation
          </button>
          <div className="conv-list-search">
            <Search className="size-3 shrink-0" aria-hidden />
            <input
              type="search"
              placeholder="Search…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label="Search conversations"
            />
          </div>
          <div className="flex items-center justify-end">
            {!selectionMode ? (
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => setSelectionMode(true)}
                title="Select conversations"
                aria-label="Select conversations"
                style={{ fontSize: 11, padding: '0 6px', height: 22 }}
              >
                <Trash2 className="size-3" aria-hidden />
                Select
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => { setSelectionMode(false); setSelectedIds(new Set()) }}
                style={{ fontSize: 11, padding: '0 6px', height: 22 }}
              >
                Cancel
              </button>
            )}
          </div>
        </div>
      )}

      {selectionMode && (
        <div className="flex items-center justify-between gap-2 px-3 py-2" style={{ borderBottom: '1px solid var(--line)', background: 'var(--bg-2)', fontSize: 12 }}>
          <label className="inline-flex items-center gap-1.5">
            <input
              ref={selectAllRef}
              type="checkbox"
              className="size-3.5 rounded"
              checked={allSelected}
              onChange={() => {
                if (allSelected) setSelectedIds(new Set())
                else setSelectedIds(new Set(conversationIds))
              }}
              aria-label="Select all conversations"
            />
            <span style={{ color: 'var(--ink-2)' }}>{selectedCount} selected</span>
          </label>
          <button
            type="button"
            data-testid="sidebar-bulk-delete"
            disabled={selectedCount === 0 || bulkDeleteMut.isPending}
            className="btn btn-sm"
            style={{ color: '#ef4444' }}
            onClick={() => {
              const ids = Array.from(selectedIds)
              if (ids.length === 0) return
              setConfirmDelete({ kind: 'bulk', ids })
            }}
          >
            <Trash2 className="size-3" aria-hidden />
            Delete
          </button>
        </div>
      )}

      {conversationsError && (
        <p className="px-3 py-2 text-sm text-red-600">{conversationsError.message}</p>
      )}
      {singleDeleteMut.isError && (
        <p className="px-3 py-2 text-sm text-red-600">{(singleDeleteMut.error as Error).message}</p>
      )}
      {bulkDeleteMut.isError && (
        <p className="px-3 py-2 text-sm text-red-600">{(bulkDeleteMut.error as Error).message}</p>
      )}

      <div className="conv-list-scroll">
        {conversationsPending && <PrismLogo state="loading" size={16} className="mx-auto my-3" />}

        {groups.today.length > 0 && (
          <>
            <div className="conv-grp-label">Today</div>
            {groups.today.map(renderConvRow)}
          </>
        )}
        {groups.yesterday.length > 0 && (
          <>
            <div className="conv-grp-label">Yesterday</div>
            {groups.yesterday.map(renderConvRow)}
          </>
        )}
        {groups.earlier.length > 0 && (
          <>
            <div className="conv-grp-label">Earlier</div>
            {groups.earlier.map(renderConvRow)}
          </>
        )}
        {!conversationsPending && filteredConvs.length === 0 && (
          <p className="px-3 py-4 text-xs" style={{ color: 'var(--ink-3)' }}>
            {searchQuery ? 'No conversations match.' : 'No conversations yet.'}
          </p>
        )}
      </div>

      {confirmDelete && (
        <div
          className="fixed inset-0 z-60 flex items-center justify-center bg-black/45 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-conversation-title"
          onClick={(e) => e.target === e.currentTarget && setConfirmDelete(null)}
        >
          <div
            className="w-full max-w-md rounded-xl border border-neutral-200 bg-white p-4 shadow-xl dark:border-neutral-700 dark:bg-neutral-950"
            onClick={(e) => e.stopPropagation()}
          >
            <h2
              id="delete-conversation-title"
              className="text-base font-semibold text-neutral-900 dark:text-neutral-100"
            >
              {confirmDelete.kind === 'bulk' ? 'Delete selected conversations?' : 'Delete conversation?'}
            </h2>
            <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-300">
              This action cannot be undone.
            </p>
            {confirmDelete.kind === 'single' ? (
              <p className="mt-2 line-clamp-1 rounded-md border border-neutral-200 bg-neutral-50 px-2 py-1 text-xs text-neutral-700 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-300">
                {confirmDelete.label}
              </p>
            ) : (
              <p className="mt-2 text-xs text-neutral-500 dark:text-neutral-400">
                {confirmDelete.ids.length} conversation(s) will be removed.
              </p>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border border-neutral-300 px-3 py-1.5 text-sm dark:border-neutral-600"
                onClick={() => setConfirmDelete(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-lg bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-500 disabled:opacity-50"
                disabled={singleDeleteMut.isPending || bulkDeleteMut.isPending}
                onClick={() => {
                  if (confirmDelete.kind === 'single') {
                    singleDeleteMut.mutate(confirmDelete.id)
                    return
                  }
                  bulkDeleteMut.mutate(confirmDelete.ids)
                }}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}
