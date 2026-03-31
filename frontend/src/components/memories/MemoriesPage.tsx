import { Plus, Trash2 } from 'lucide-react'
import * as React from 'react'

import {
  useCreateMemory,
  useDeleteMemory,
  useMemoriesQuery,
  useUpdateMemory,
} from '~/hooks/useMemoriesQuery'
import { cn } from '~/lib/utils'

export function MemoriesPage() {
  const memoriesQ = useMemoriesQuery()
  const createMut = useCreateMemory()
  const updateMut = useUpdateMemory()
  const deleteMut = useDeleteMemory()
  const [draft, setDraft] = React.useState('')

  const handleCreate = () => {
    const text = draft.trim()
    if (!text) return
    createMut.mutate(text, { onSuccess: () => setDraft('') })
  }

  return (
    <div className="mx-auto min-h-0 w-full max-w-3xl flex-1 space-y-6 overflow-y-auto overscroll-contain p-4 sm:p-6">
      <header>
        <h1 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Memories</h1>
        <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
          Persistent facts the assistant remembers about you. Active memories are included in every
          conversation.
        </p>
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

      <section>
        <h2 className="mb-3 text-sm font-medium text-neutral-900 dark:text-neutral-100">
          Your memories
        </h2>

        {memoriesQ.isPending && <p className="text-sm text-neutral-500">Loading…</p>}
        {memoriesQ.isError && (
          <p className="text-sm text-red-600">{(memoriesQ.error as Error).message}</p>
        )}
        {memoriesQ.data && memoriesQ.data.length === 0 && (
          <p className="text-sm text-neutral-500">
            No memories yet. Add one above or chat with the assistant — it will learn from your
            conversations automatically.
          </p>
        )}
        {memoriesQ.data && memoriesQ.data.length > 0 && (
          <ul className="space-y-2">
            {memoriesQ.data.map((m) => (
              <li
                key={m.id}
                className={cn(
                  'flex items-start gap-3 rounded-xl border p-3 transition-colors',
                  m.is_active
                    ? 'border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900'
                    : 'border-neutral-100 bg-neutral-50 opacity-60 dark:border-neutral-800/60 dark:bg-neutral-900/40',
                )}
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-neutral-900 dark:text-neutral-100">{m.content}</p>
                  <div className="mt-1 flex items-center gap-2 text-[10px] text-neutral-400">
                    <span
                      className={cn(
                        'rounded-full px-1.5 py-0.5 font-medium',
                        m.source === 'auto'
                          ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300'
                          : 'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400',
                      )}
                    >
                      {m.source}
                    </span>
                    <time dateTime={m.created_at}>
                      {new Date(m.created_at).toLocaleDateString()}
                    </time>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    className={cn(
                      'rounded-md px-2 py-1 text-xs font-medium transition-colors',
                      m.is_active
                        ? 'text-amber-700 hover:bg-amber-50 dark:text-amber-400 dark:hover:bg-amber-950/40'
                        : 'text-green-700 hover:bg-green-50 dark:text-green-400 dark:hover:bg-green-950/40',
                    )}
                    disabled={updateMut.isPending}
                    onClick={() =>
                      updateMut.mutate({ id: m.id, is_active: !m.is_active })
                    }
                  >
                    {m.is_active ? 'Pause' : 'Resume'}
                  </button>
                  <button
                    type="button"
                    className="rounded p-1 text-neutral-400 hover:bg-neutral-200 hover:text-red-600 dark:hover:bg-neutral-800 dark:hover:text-red-400"
                    title="Delete memory"
                    disabled={deleteMut.isPending}
                    onClick={() => {
                      if (window.confirm('Delete this memory?')) {
                        deleteMut.mutate(m.id)
                      }
                    }}
                  >
                    <Trash2 className="size-3.5" aria-hidden />
                    <span className="sr-only">Delete</span>
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
