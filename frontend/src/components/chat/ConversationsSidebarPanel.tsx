import { Link } from '@tanstack/react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { MoreHorizontal, Plus, Trash2 } from 'lucide-react'
import * as React from 'react'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import type { Conversation } from '~/lib/chat-types'
import { queryKeys } from '~/lib/queryKeys'

type ConversationsSidebarPanelProps = {
  conversations: Conversation[] | undefined
  conversationsPending: boolean
  conversationsError: Error | null
  onNewConversation: () => void
}

export function ConversationsSidebarPanel({
  conversations,
  conversationsPending,
  conversationsError,
  onNewConversation,
}: ConversationsSidebarPanelProps) {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  const [menuOpen, setMenuOpen] = React.useState(false)
  const [selectionMode, setSelectionMode] = React.useState(false)
  const [selectedIds, setSelectedIds] = React.useState<Set<number>>(new Set())
  const [confirmDelete, setConfirmDelete] = React.useState<
    | { kind: 'single'; id: number; label: string }
    | { kind: 'bulk'; ids: number[] }
    | null
  >(null)
  const selectAllRef = React.useRef<HTMLInputElement | null>(null)
  const conversationIds = React.useMemo(() => (conversations ?? []).map((c) => c.id), [conversations])

  const closeMenu = () => setMenuOpen(false)
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
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.conversations() })
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
    onSuccess: () => {
      setSelectedIds(new Set())
      setSelectionMode(false)
      void qc.invalidateQueries({ queryKey: queryKeys.conversations() })
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

  return (
    <aside className="flex w-full shrink-0 flex-col gap-2 border-b border-neutral-200 p-3 dark:border-neutral-800 md:h-full md:min-h-0 md:w-64 md:max-w-64 md:overflow-y-auto md:border-b-0 md:border-r md:overscroll-contain">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold">Conversations</span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-neutral-900 text-white hover:bg-neutral-800 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
            onClick={onNewConversation}
            title="New conversation"
            aria-label="New conversation"
          >
            <Plus className="size-4" aria-hidden />
          </button>
          <div className="relative">
            <button
              type="button"
              className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-neutral-200 bg-white text-neutral-700 hover:bg-neutral-100 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-200 dark:hover:bg-neutral-900"
              onClick={() => setMenuOpen((v) => !v)}
              title="Conversation actions"
              aria-label="Conversation actions"
              aria-expanded={menuOpen}
              aria-haspopup="menu"
            >
              <MoreHorizontal className="size-4" aria-hidden />
            </button>
            {menuOpen && (
              <div
                role="menu"
                className="absolute right-0 top-8 z-20 min-w-44 rounded-md border border-neutral-200 bg-white p-1 shadow-lg dark:border-neutral-700 dark:bg-neutral-950"
              >
                <button
                  type="button"
                  role="menuitem"
                  className="w-full rounded px-2 py-1.5 text-left text-xs text-neutral-700 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-900"
                  onClick={() => {
                    setSelectionMode(true)
                    closeMenu()
                  }}
                >
                  Select conversations
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
      {selectionMode && (
        <div className="space-y-2 rounded-md border border-neutral-200 bg-neutral-50 px-3 py-2 text-xs dark:border-neutral-700 dark:bg-neutral-900">
          <div className="flex items-center justify-between gap-2">
            <label className="inline-flex items-center gap-1.5 whitespace-nowrap text-neutral-600 dark:text-neutral-300">
              <input
                ref={selectAllRef}
                type="checkbox"
                className="size-3.5 rounded border-neutral-300 dark:border-neutral-600"
                checked={allSelected}
                onChange={() => {
                  if (allSelected) {
                    setSelectedIds(new Set())
                  } else {
                    setSelectedIds(new Set(conversationIds))
                  }
                }}
                aria-label="Select all conversations"
              />
              <span>Select all</span>
            </label>
            <span className="whitespace-nowrap text-neutral-500 dark:text-neutral-400">
              {selectedCount} selected
            </span>
          </div>
          <div className="flex items-center justify-end gap-1">
            <button
              type="button"
              className="rounded px-2 py-1 text-neutral-600 hover:bg-neutral-200 dark:text-neutral-300 dark:hover:bg-neutral-800"
              onClick={() => {
                setSelectionMode(false)
                setSelectedIds(new Set())
              }}
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={selectedCount === 0 || bulkDeleteMut.isPending}
              className="inline-flex items-center gap-1 rounded bg-red-600 px-2 py-1 text-white disabled:cursor-not-allowed disabled:opacity-50"
              onClick={() => {
                const ids = Array.from(selectedIds)
                if (ids.length === 0) return
                setConfirmDelete({ kind: 'bulk', ids })
              }}
            >
              <Trash2 className="size-3.5" aria-hidden />
              Delete
            </button>
          </div>
        </div>
      )}
      {conversationsPending && <p className="text-sm text-neutral-500">Loading…</p>}
      {conversationsError && (
        <p className="text-sm text-red-600">{conversationsError.message}</p>
      )}
      {singleDeleteMut.isError && (
        <p className="text-sm text-red-600">{(singleDeleteMut.error as Error).message}</p>
      )}
      {bulkDeleteMut.isError && (
        <p className="text-sm text-red-600">{(bulkDeleteMut.error as Error).message}</p>
      )}
      <ul className="max-h-48 min-h-0 space-y-1 overflow-y-auto md:max-h-none">
        {(conversations ?? []).map((c) => (
          <li key={c.id}>
            <div className="group flex items-start gap-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-900">
              {selectionMode && (
                <label className="mt-1.5 inline-flex shrink-0 items-center pl-1">
                  <input
                    type="checkbox"
                    className="size-3.5 rounded border-neutral-300 dark:border-neutral-600"
                    checked={selectedIds.has(c.id)}
                    onChange={() => toggleSelected(c.id)}
                    aria-label={`Select conversation ${c.title ?? c.id}`}
                  />
                </label>
              )}
              <Link
                to="/chat/conversations/$id"
                params={{ id: String(c.id) }}
                className="min-w-0 flex-1 truncate rounded px-2 py-1 text-left text-sm"
                activeProps={{
                  className:
                    'min-w-0 flex-1 truncate rounded px-2 py-1 text-left text-sm bg-neutral-200 dark:bg-neutral-800',
                }}
              >
                <span
                  className={
                    c.title
                      ? 'block truncate'
                      : 'block truncate text-neutral-600 dark:text-neutral-400'
                  }
                >
                  {c.title ?? 'New conversation'}
                </span>
                {c.assistant_id != null && (
                  <span className="block truncate text-[10px] text-neutral-500">
                    Assistant #{c.assistant_id}
                  </span>
                )}
              </Link>
              <button
                type="button"
                className="mr-1 mt-1 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded text-neutral-400 opacity-0 transition hover:bg-red-50 hover:text-red-600 group-hover:opacity-100 dark:hover:bg-red-950/40 dark:hover:text-red-400"
                title="Delete conversation"
                onClick={() => {
                  setConfirmDelete({
                    kind: 'single',
                    id: c.id,
                    label: c.title?.trim() || `Conversation #${c.id}`,
                  })
                }}
              >
                <Trash2 className="size-3.5" aria-hidden />
                <span className="sr-only">Delete</span>
              </button>
            </div>
          </li>
        ))}
      </ul>
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
                    singleDeleteMut.mutate(confirmDelete.id, { onSuccess: () => setConfirmDelete(null) })
                    return
                  }
                  bulkDeleteMut.mutate(confirmDelete.ids, { onSuccess: () => setConfirmDelete(null) })
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
