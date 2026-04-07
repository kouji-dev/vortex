import { Plus, Search, Trash2 } from 'lucide-react'
import * as React from 'react'

import { TableShell } from '~/components/ui/TableShell'
import {
  useCreateMemory,
  useDeleteMemory,
  useMemoriesInfiniteQuery,
  useUpdateMemory,
} from '~/hooks/useMemoriesQuery'
import { cn } from '~/lib/utils'

export function MemoriesPage() {
  const memoriesQ = useMemoriesInfiniteQuery(25)
  const createMut = useCreateMemory()
  const updateMut = useUpdateMemory()
  const deleteMut = useDeleteMemory()
  const [draft, setDraft] = React.useState('')
  const [search, setSearch] = React.useState('')
  const [pendingDelete, setPendingDelete] = React.useState<{ id: number; content: string } | null>(
    null,
  )

  const handleCreate = () => {
    const text = draft.trim()
    if (!text) return
    createMut.mutate(text, { onSuccess: () => setDraft('') })
  }

  const formatDate = (iso: string) => {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return '—'
    return d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
    })
  }

  const memories = React.useMemo(
    () => memoriesQ.data?.pages.flatMap((p) => p.items) ?? [],
    [memoriesQ.data],
  )
  const filteredMemories = React.useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return memories
    return memories.filter((m) => {
      const haystack = [
        m.content,
        m.source,
        m.is_active ? 'active' : 'paused',
        m.created_at,
        m.updated_at,
        m.is_system ? 'system profile main auto-maintained' : 'manual',
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(q)
    })
  }, [memories, search])

  const orderedFilteredMemories = React.useMemo(() => {
    return [...filteredMemories].sort(
      (a, b) => Number(b.is_system) - Number(a.is_system) || b.id - a.id,
    )
  }, [filteredMemories])
  const loadMoreRef = React.useRef<HTMLDivElement | null>(null)
  const tableScrollRef = React.useRef<HTMLDivElement | null>(null)

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
      { root: tableScrollRef.current, rootMargin: '200px' },
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [memoriesQ])
  const activeCount = memories.filter((m) => m.is_active).length
  const profileRowCount = memories.filter((m) => m.is_system).length

  return (
    <>
    <div className="page-enter mx-auto min-h-0 w-full max-w-6xl flex-1 space-y-6 overflow-hidden p-4 sm:p-6">
      <header>
        <h1 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Memories</h1>
        <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
          One profile row per account is auto-updated from your chats and used when active. Manual
          memories are the ones you add below; active manual rows are included in conversations.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-full border border-neutral-200 bg-white px-2.5 py-1 text-neutral-600 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-300">
            Total: <span className="font-semibold tabular-nums">{memories.length}</span>
          </span>
          <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-emerald-700 dark:border-emerald-800/60 dark:bg-emerald-950/30 dark:text-emerald-300">
            Active: <span className="font-semibold tabular-nums">{activeCount}</span>
          </span>
          <span className="rounded-full border border-purple-200 bg-purple-50 px-2.5 py-1 text-purple-700 dark:border-purple-800/60 dark:bg-purple-950/30 dark:text-purple-300">
            Profile row: <span className="font-semibold tabular-nums">{profileRowCount}</span>
          </span>
        </div>
      </header>

      <section className="rounded-xl border border-neutral-200 bg-neutral-50/80 p-4 dark:border-neutral-800 dark:bg-neutral-900/40">
        <h2 className="mb-3 text-sm font-medium text-neutral-900 dark:text-neutral-100">
          Add a memory
        </h2>
        <div className="flex gap-2">
          <input
            className="flex-1 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
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
            disabled={createMut.isPending || !draft.trim()}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold transition-colors',
              'border border-blue-600 bg-blue-600 text-white shadow-sm hover:bg-blue-500',
              'disabled:cursor-not-allowed disabled:opacity-50',
            )}
            onClick={handleCreate}
          >
            <Plus className="size-4" aria-hidden />
            Add
          </button>
        </div>
        {createMut.isError && (
          <p className="mt-2 text-sm text-red-600">
            {(createMut.error as Error).message}
          </p>
        )}
      </section>

      <section className="flex min-h-0 flex-1 flex-col">
        <h2 className="mb-3 text-sm font-medium text-neutral-900 dark:text-neutral-100">
          Your memories
        </h2>
        <div className="mb-2 flex items-center gap-2 rounded-lg border border-neutral-200 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-950">
          <Search className="size-4 shrink-0 text-neutral-400" aria-hidden />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search memories..."
            className="min-w-0 flex-1 bg-transparent text-sm text-neutral-900 placeholder-neutral-400 outline-none dark:text-neutral-100"
            aria-label="Search memories"
          />
        </div>

        {memoriesQ.isPending && <p className="text-sm text-neutral-500">Loading…</p>}
        {memoriesQ.isError && (
          <p className="text-sm text-red-600">{(memoriesQ.error as Error).message}</p>
        )}
        {!memoriesQ.isPending && memories.length === 0 && (
          <p className="text-sm text-neutral-500">
            No memories yet. Add a manual memory above, or chat — a profile row will be created and
            updated automatically from your conversations.
          </p>
        )}
        {!memoriesQ.isPending && memories.length > 0 && filteredMemories.length === 0 && (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">No memories match your search.</p>
        )}
        {orderedFilteredMemories.length > 0 && (
          <TableShell className="flex-1" containerRef={tableScrollRef}>
            <table className="w-full min-w-[62rem] text-left text-sm">
              <thead className="sticky top-0 z-10 border-b border-neutral-200 bg-neutral-50 text-xs text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400">
                <tr>
                  <th className="px-4 py-2 font-medium">Memory</th>
                  <th className="px-4 py-2 font-medium">Type</th>
                  <th className="px-4 py-2 font-medium">Source</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Created</th>
                  <th className="px-4 py-2 font-medium">Last updated</th>
                  <th className="px-4 py-2 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
                {orderedFilteredMemories.map((m) => (
                  <tr
                    key={m.id}
                    className={cn(
                      'align-top hover:bg-neutral-50 dark:hover:bg-neutral-900/60',
                      !m.is_active && 'opacity-70',
                      m.is_system &&
                        'bg-purple-50/40 dark:bg-purple-950/15',
                    )}
                  >
                    <td className="px-4 py-2.5 text-neutral-900 dark:text-neutral-100">
                      <p className="line-clamp-2">{m.content}</p>
                      {m.is_system && (
                        <p className="mt-1 text-[11px] text-purple-700 dark:text-purple-300">
                          Main profile memory — updated from your conversations when active.
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      {m.is_system ? (
                        <span
                          data-testid="memory-system-badge"
                          className="inline-flex rounded-full border border-violet-300 bg-violet-100 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-violet-900 dark:border-violet-700 dark:bg-violet-950/60 dark:text-violet-200"
                        >
                          System
                        </span>
                      ) : (
                        <span className="text-xs text-neutral-500 dark:text-neutral-400">Manual</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={cn(
                          'inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium',
                          m.is_system
                            ? 'border-purple-200 bg-purple-50 text-purple-700 dark:border-purple-800/60 dark:bg-purple-950/30 dark:text-purple-300'
                            : 'border-neutral-200 bg-neutral-100 text-neutral-600 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-300',
                        )}
                      >
                        {m.source}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={cn(
                          'inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium',
                          m.is_active
                            ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800/60 dark:bg-emerald-950/30 dark:text-emerald-300'
                            : 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800/60 dark:bg-amber-950/30 dark:text-amber-300',
                        )}
                      >
                        {m.is_active ? 'Active' : 'Paused'}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-neutral-700 dark:text-neutral-300">
                      <time dateTime={m.created_at}>{formatDate(m.created_at)}</time>
                    </td>
                    <td className="px-4 py-2.5 text-neutral-700 dark:text-neutral-300">
                      <time dateTime={m.updated_at}>{formatDate(m.updated_at)}</time>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex justify-end gap-1">
                        <button
                          type="button"
                          className={cn(
                            'rounded-md px-2 py-1 text-xs font-medium transition-colors',
                            m.is_active
                              ? 'text-amber-700 hover:bg-amber-50 dark:text-amber-400 dark:hover:bg-amber-950/40'
                              : 'text-green-700 hover:bg-green-50 dark:text-green-400 dark:hover:bg-green-950/40',
                          )}
                          disabled={updateMut.isPending}
                          onClick={() => updateMut.mutate({ id: m.id, is_active: !m.is_active })}
                        >
                          {m.is_active ? 'Pause' : 'Resume'}
                        </button>
                        <button
                          type="button"
                          className="rounded p-1 text-neutral-400 hover:bg-neutral-200 hover:text-red-600 dark:hover:bg-neutral-800 dark:hover:text-red-400"
                          title="Delete memory"
                          disabled={deleteMut.isPending}
                          onClick={() => {
                            setPendingDelete({ id: m.id, content: m.content })
                          }}
                        >
                          <Trash2 className="size-3.5" aria-hidden />
                          <span className="sr-only">Delete</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div ref={loadMoreRef} className="h-1" />
            {memoriesQ.isFetchingNextPage && (
              <p className="px-4 py-2 text-xs text-neutral-500">Loading more...</p>
            )}
          </TableShell>
        )}
      </section>
    </div>
    {pendingDelete && (
      <div
        className="fixed inset-0 z-60 flex items-center justify-center bg-black/45 p-4"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-memory-title"
        onClick={(e) => e.target === e.currentTarget && setPendingDelete(null)}
      >
        <div
          className="w-full max-w-md rounded-xl border border-neutral-200 bg-white p-4 shadow-xl dark:border-neutral-700 dark:bg-neutral-950"
          onClick={(e) => e.stopPropagation()}
        >
          <h2 id="delete-memory-title" className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
            Delete memory?
          </h2>
          <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-300">
            This action cannot be undone.
          </p>
          <p className="mt-2 line-clamp-2 rounded-md border border-neutral-200 bg-neutral-50 px-2 py-1 text-xs text-neutral-700 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-300">
            {pendingDelete.content}
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <button
              type="button"
              className="rounded-lg border border-neutral-300 px-3 py-1.5 text-sm dark:border-neutral-600"
              onClick={() => setPendingDelete(null)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="rounded-lg bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-500 disabled:opacity-50"
              disabled={deleteMut.isPending}
              onClick={() => {
                deleteMut.mutate(pendingDelete.id, {
                  onSuccess: () => setPendingDelete(null),
                })
              }}
            >
              Delete
            </button>
          </div>
        </div>
      </div>
    )}
    </>
  )
}
