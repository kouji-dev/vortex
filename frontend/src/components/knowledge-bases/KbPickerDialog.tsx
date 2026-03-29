import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'

function fuzzyMatch(name: string, query: string): boolean {
  if (!query) return true
  const n = name.toLowerCase()
  const q = query.toLowerCase()
  let qi = 0
  for (let i = 0; i < n.length && qi < q.length; i++) {
    if (n[i] === q[qi]) qi++
  }
  return qi === q.length
}

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import type { Conversation } from '~/lib/chat-types'
import {
  knowledgeBaseListFromResponse,
  parseKnowledgeBasesListJson,
} from '~/lib/knowledge-base-types'
import { queryKeys } from '~/lib/queryKeys'

interface KbPickerDialogProps {
  conversationId: number
  open: boolean
  onClose: () => void
}

export function KbPickerDialog({ conversationId, open, onClose }: KbPickerDialogProps) {
  const apiBase = getApiBase()
  const qc = useQueryClient()

  const [search, setSearch] = React.useState('')
  const [activeIndex, setActiveIndex] = React.useState(0)

  const inputRef = React.useRef<HTMLInputElement>(null)

  // Fetch all KBs
  const listQ = useQuery({
    queryKey: queryKeys.knowledgeBases(),
    queryFn: async () => {
      const res = await fetch(`${apiBase}/api/knowledge-bases`, {
        headers: await getAuthHeaders(),
      })
      const text = await res.text()
      return knowledgeBaseListFromResponse(res, text, parseKnowledgeBasesListJson)
    },
    enabled: open,
  })

  // Get currently attached KB IDs from cached conversation
  const conversation = qc.getQueryData<Conversation>(queryKeys.conversation(conversationId))
  const attachedIds = conversation?.knowledge_base_ids ?? []

  const saveMut = useMutation({
    mutationFn: async (ids: number[]) => {
      const res = await fetch(
        `${apiBase}/api/chat/conversations/${conversationId}/knowledge-bases`,
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            ...(await getAuthHeaders()),
          },
          body: JSON.stringify({ knowledge_base_ids: ids }),
        },
      )
      if (!res.ok) throw new Error(await res.text())
      return res.json() as Promise<Conversation>
    },
    onSuccess: (data) => {
      void qc.setQueryData(queryKeys.conversation(conversationId), data)
      void qc.invalidateQueries({ queryKey: queryKeys.conversations() })
    },
  })

  const allKbs = listQ.data ?? []

  // Sort: attached first, then alphabetical
  const sorted = React.useMemo(() => {
    const attached = allKbs.filter((kb) => attachedIds.includes(kb.id))
    const unattached = allKbs.filter((kb) => !attachedIds.includes(kb.id))
    return [...attached, ...unattached]
  }, [allKbs, attachedIds])

  const filtered = React.useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return sorted
    return sorted.filter((kb) => fuzzyMatch(kb.name, q))
  }, [sorted, search])

  // Reset active index when filtered list changes
  React.useEffect(() => {
    setActiveIndex(0)
  }, [filtered.length, search])

  // Auto-focus input when dialog opens
  React.useEffect(() => {
    if (open) {
      setSearch('')
      setActiveIndex(0)
      // Small delay to ensure DOM is rendered
      const t = setTimeout(() => inputRef.current?.focus(), 50)
      return () => clearTimeout(t)
    }
  }, [open])

  const toggle = React.useCallback(
    (kbId: number) => {
      const next = attachedIds.includes(kbId)
        ? attachedIds.filter((id) => id !== kbId)
        : [...attachedIds, kbId]
      saveMut.mutate(next)
    },
    [attachedIds, saveMut],
  )

  const handleKeyDown = React.useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setActiveIndex((i) => Math.min(i + 1, filtered.length - 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActiveIndex((i) => Math.max(i - 1, 0))
      } else if (e.key === 'Enter') {
        e.preventDefault()
        const kb = filtered[activeIndex]
        if (kb) toggle(kb.id)
      } else if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    },
    [filtered, activeIndex, toggle, onClose],
  )

  if (!open) return null

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 pt-[15vh]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      {/* Panel */}
      <div
        className="w-full max-w-lg overflow-hidden rounded-xl border border-neutral-200 bg-white shadow-2xl dark:border-neutral-700 dark:bg-neutral-900"
        onKeyDown={handleKeyDown}
      >
        {/* Search input */}
        <div className="flex items-center gap-2 border-b border-neutral-200 px-4 py-3 dark:border-neutral-700">
          <span className="shrink-0 text-neutral-400" aria-hidden>
            🔍
          </span>
          <input
            ref={inputRef}
            type="text"
            placeholder="Search knowledge bases…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="min-w-0 flex-1 bg-transparent text-sm text-neutral-900 placeholder-neutral-400 outline-none dark:text-neutral-100"
          />
          {saveMut.isPending && (
            <span className="shrink-0 text-xs text-neutral-400">Saving…</span>
          )}
        </div>

        {/* List */}
        <ul
          role="listbox"
          className="max-h-72 overflow-y-auto py-1"
          aria-label="Knowledge bases"
        >
          {listQ.isPending && (
            <li className="px-4 py-3 text-sm text-neutral-400">Loading…</li>
          )}
          {listQ.isError && (
            <li className="px-4 py-3 text-sm text-red-500">
              {(listQ.error as Error).message}
            </li>
          )}
          {!listQ.isPending && filtered.length === 0 && (
            <li className="px-4 py-3 text-sm text-neutral-400">No knowledge bases found.</li>
          )}
          {filtered.map((kb, idx) => {
            const isAttached = attachedIds.includes(kb.id)
            const isActive = idx === activeIndex
            return (
              <li
                key={kb.id}
                role="option"
                aria-selected={isAttached}
                onMouseEnter={() => setActiveIndex(idx)}
                onClick={() => toggle(kb.id)}
                className={[
                  'flex cursor-pointer select-none items-center gap-3 px-4 py-2.5 text-sm',
                  isActive
                    ? 'bg-neutral-100 dark:bg-neutral-800'
                    : 'hover:bg-neutral-50 dark:hover:bg-neutral-800/50',
                ].join(' ')}
              >
                {/* KB icon */}
                <span className="shrink-0 text-base" aria-hidden>
                  📄
                </span>

                {/* Name + doc count */}
                <span className="min-w-0 flex-1 truncate text-neutral-900 dark:text-neutral-100">
                  {kb.name}
                </span>
                <span className="shrink-0 text-xs text-neutral-400">
                  {kb.document_count != null ? `${kb.document_count} docs` : '–'}
                </span>

                {/* Active indicator */}
                {isAttached && (
                  <span className="shrink-0 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                    ● active
                  </span>
                )}
              </li>
            )
          })}
        </ul>

        {/* Footer hint */}
        <div className="border-t border-neutral-200 px-4 py-2 text-xs text-neutral-400 dark:border-neutral-700">
          ↑↓ navigate · enter toggle · esc close
        </div>
      </div>
    </div>
  )
}
