import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import { Check, Search } from 'lucide-react'
import { PrismLogo } from '~/components/brand'

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
      className="kb-menu overflow-hidden"
      onKeyDown={handleKeyDown}
      data-testid="kb-picker-popover-inner"
      style={{
        background: 'var(--panel)',
        border: '1px solid var(--line)',
        borderRadius: 6,
        boxShadow: 'var(--shadow-md)',
      }}
    >
      <div
        className="menu-head"
        style={{ gap: 8 }}
      >
        <span>Knowledge bases</span>
        <span className="mono muted" style={{ fontWeight: 400 }}>
          {listQ.data?.length ?? 0} available
        </span>
      </div>

      <div
        className="flex items-center gap-2 px-3 py-2"
        style={{ borderBottom: '1px solid var(--line-2)' }}
      >
        <Search className="size-3 shrink-0" strokeWidth={2} style={{ color: 'var(--ink-3)' }} aria-hidden />
        <input
          ref={inputRef}
          type="text"
          placeholder="Search knowledge bases…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          data-testid="kb-picker-search"
          className="min-w-0 flex-1 bg-transparent outline-none"
          style={{ fontSize: 12, color: 'var(--ink)' }}
        />
        {conversationId != null && saveMut.isPending && (
          <PrismLogo state="loading" size={12} />
        )}
      </div>

      <ul
        role="listbox"
        className="menu-scroll"
        aria-label="Knowledge bases"
        style={{ margin: 0, padding: 0, listStyle: 'none' }}
      >
        {listQ.isPending && (
          <li className="px-3 py-3"><PrismLogo state="loading" size={16} /></li>
        )}
        {listQ.isError && (
          <li className="px-3 py-3" style={{ fontSize: 12, color: 'var(--err)' }}>
            {(listQ.error as Error).message}
          </li>
        )}
        {!listQ.isPending && filtered.length === 0 && (
          <li className="px-3 py-3" style={{ fontSize: 12, color: 'var(--ink-3)' }}>
            No knowledge bases found.
          </li>
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
              className={`kb-menu-row ${isAttached ? 'on' : ''}`}
              style={isActiveRow ? { background: 'var(--bg-2)' } : undefined}
            >
              <div className={`box ${isAttached ? 'on' : ''}`}>
                {isAttached && <Check className="size-2.5" strokeWidth={3} aria-hidden />}
              </div>
              <div className="kb-main">
                <div className="kb-name truncate">{kb.name}</div>
                <div className="kb-meta">
                  {isAttached && <span className="mr-1 font-medium" style={{ color: 'var(--accent)' }}>Active</span>}
                  {kb.document_count != null ? `${kb.document_count} docs` : '—'}
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
