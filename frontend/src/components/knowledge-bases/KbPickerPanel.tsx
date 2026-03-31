import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import { CheckCircle2, FileText, Loader2, Search } from 'lucide-react'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import type { Conversation } from '~/lib/chat-types'
import {
  knowledgeBaseListFromResponse,
  parseKnowledgeBasesListJson,
} from '~/lib/knowledge-base-types'
import { queryKeys } from '~/lib/queryKeys'

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

export type KbPickerPanelProps = {
  /**
   * Persisted thread: server sync via PUT. `null` = new chat (draft IDs only).
   */
  conversationId: number | null
  draftKnowledgeBaseIds?: number[]
  onDraftKnowledgeBaseIdsChange?: (ids: number[]) => void
  /** When false, list query is disabled (popover closed). */
  open: boolean
  onRequestClose: () => void
}

export function KbPickerPanel({
  conversationId,
  draftKnowledgeBaseIds = [],
  onDraftKnowledgeBaseIdsChange,
  open,
  onRequestClose,
}: KbPickerPanelProps) {
  const apiBase = getApiBase()
  const qc = useQueryClient()

  const [search, setSearch] = React.useState('')
  const [activeIndex, setActiveIndex] = React.useState(0)

  const inputRef = React.useRef<HTMLInputElement>(null)

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

  const persistedConv =
    conversationId != null
      ? qc.getQueryData<Conversation>(queryKeys.conversation(conversationId))
      : undefined
  const attachedIds =
    conversationId != null
      ? (persistedConv?.knowledge_base_ids ?? [])
      : draftKnowledgeBaseIds

  const saveMut = useMutation({
    mutationFn: async (ids: number[]) => {
      if (conversationId == null) {
        throw new Error('KbPickerPanel: draft mode does not use PUT')
      }
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
      if (conversationId == null) return
      void qc.setQueryData(queryKeys.conversation(conversationId), data)
      void qc.invalidateQueries({ queryKey: queryKeys.conversations() })
    },
  })

  const allKbs = listQ.data ?? []

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

  React.useEffect(() => {
    setActiveIndex(0)
  }, [filtered.length, search])

  React.useEffect(() => {
    if (open) {
      setSearch('')
      setActiveIndex(0)
      const t = setTimeout(() => inputRef.current?.focus(), 50)
      return () => clearTimeout(t)
    }
  }, [open])

  const toggle = React.useCallback(
    (kbId: number) => {
      const next = attachedIds.includes(kbId)
        ? attachedIds.filter((id) => id !== kbId)
        : [...attachedIds, kbId]
      if (conversationId != null) {
        saveMut.mutate(next)
      } else {
        onDraftKnowledgeBaseIdsChange?.(next)
      }
    },
    [attachedIds, conversationId, onDraftKnowledgeBaseIdsChange, saveMut],
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
        onRequestClose()
      }
    },
    [filtered, activeIndex, toggle, onRequestClose],
  )

  return (
    <div
      className="overflow-hidden rounded-lg border border-neutral-200 bg-white shadow-lg dark:border-neutral-700 dark:bg-neutral-950"
      onKeyDown={handleKeyDown}
      data-testid="kb-picker-popover-inner"
    >
      <div className="flex items-center gap-2 border-b border-neutral-200 px-3 py-2 dark:border-neutral-700">
        <Search className="size-3.5 shrink-0 text-neutral-400" aria-hidden />
        <input
          ref={inputRef}
          type="text"
          placeholder="Search knowledge bases…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          data-testid="kb-picker-search"
          className="min-w-0 flex-1 bg-transparent text-sm text-neutral-900 placeholder-neutral-400 outline-none dark:text-neutral-100"
        />
        {conversationId != null && saveMut.isPending && (
          <span className="inline-flex items-center gap-1 text-xs text-neutral-400">
            <Loader2 className="size-3 animate-spin" aria-hidden />
            Saving...
          </span>
        )}
      </div>

      <ul
        role="listbox"
        className="max-h-72 overflow-y-auto py-1"
        aria-label="Knowledge bases"
      >
        {listQ.isPending && (
          <li className="px-3 py-3 text-sm text-neutral-400">Loading...</li>
        )}
        {listQ.isError && (
          <li className="px-3 py-3 text-sm text-red-500">
            {(listQ.error as Error).message}
          </li>
        )}
        {!listQ.isPending && filtered.length === 0 && (
          <li className="px-3 py-3 text-sm text-neutral-400">No knowledge bases found.</li>
        )}
        {filtered.map((kb, idx) => {
          const isAttached = attachedIds.includes(kb.id)
          const isActiveRow = idx === activeIndex
          return (
            <li
              key={kb.id}
              role="option"
              aria-selected={isAttached}
              data-testid={`kb-picker-option-${kb.id}`}
              onMouseEnter={() => setActiveIndex(idx)}
              onClick={() => toggle(kb.id)}
              className={[
                'flex cursor-pointer select-none items-center gap-2.5 px-3 py-2 text-sm',
                isActiveRow
                  ? 'bg-neutral-100 dark:bg-neutral-800'
                  : 'hover:bg-neutral-50 dark:hover:bg-neutral-800/50',
              ].join(' ')}
            >
              <FileText className="size-4 shrink-0 text-neutral-500 dark:text-neutral-400" aria-hidden />

              <span className="min-w-0 flex-1 truncate text-neutral-900 dark:text-neutral-100">
                {kb.name}
              </span>
              <span className="shrink-0 text-xs text-neutral-400">
                {kb.document_count != null ? `${kb.document_count} docs` : '–'}
              </span>

              {isAttached && (
                <span className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                  <CheckCircle2 className="size-3.5" aria-hidden />
                  Active
                </span>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
