/**
 * Chat inspector sub-panel: "Memories used in this turn".
 *
 * Backend exposes per-memory provenance via `GET /v1/memories/{id}/uses`. The
 * thread-level recall list is not yet streamed alongside the SSE — for now we
 * accept the memory ids surfaced on the assistant message (when available)
 * and resolve each one lazily.
 *
 * Until the SSE wires memory ids onto messages, this panel safely renders
 * "no memories" without breaking the existing inspector.
 */
import * as React from 'react'

import { useMemoryUsesQuery } from '~/hooks/useMemoriesV1Query'

export interface MemoriesUsedPanelProps {
  /** Memory ids that were recalled before generating the active message. */
  memoryIds?: string[]
  /** Optional source conversation id — link target for provenance. */
  conversationId?: string | null
}

export function MemoriesUsedPanel({
  memoryIds,
  conversationId,
}: MemoriesUsedPanelProps) {
  const ids = memoryIds ?? []

  if (ids.length === 0) {
    return (
      <div className="inspect-sec" data-testid="memories-used-panel-empty">
        <h4>Memories used in this turn</h4>
        <p className="text-xs" style={{ color: 'var(--ink-3)' }}>
          No memories recalled.
        </p>
      </div>
    )
  }

  return (
    <div className="inspect-sec" data-testid="memories-used-panel">
      <h4>Memories used in this turn</h4>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {ids.map((id) => (
          <MemoryRow key={id} memoryId={id} conversationId={conversationId ?? null} />
        ))}
      </ul>
    </div>
  )
}

function MemoryRow({
  memoryId,
  conversationId,
}: {
  memoryId: string
  conversationId: string | null
}) {
  const q = useMemoryUsesQuery(memoryId)

  if (q.isPending) {
    return (
      <li
        style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}
        data-testid="memory-row-loading"
      >
        loading {memoryId.slice(0, 8)}…
      </li>
    )
  }
  if (q.isError) {
    return (
      <li style={{ fontSize: 11, color: 'var(--err)' }} data-testid="memory-row-err">
        {memoryId.slice(0, 8)}: {(q.error as Error).message}
      </li>
    )
  }
  const src = q.data?.source
  const turnId = src?.turn_ids?.[0]
  return (
    <li
      data-testid="memory-row"
      data-memory-id={memoryId}
      style={{
        border: '1px solid var(--line)',
        borderRadius: 4,
        padding: '6px 8px',
        fontSize: 11,
        background: 'var(--bg-2)',
      }}
    >
      <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-3)', fontSize: 10 }}>
        {memoryId.slice(0, 8)} · {src?.extractor_model ?? 'unknown model'}
      </div>
      {src?.conversation_id && src.conversation_id !== conversationId && (
        <a
          href={`/chat/conversations/${src.conversation_id}${turnId ? `#${turnId}` : ''}`}
          style={{ fontSize: 10, color: 'var(--ink-2)', textDecoration: 'underline' }}
          data-testid="memory-row-provenance-link"
        >
          source turn ↗
        </a>
      )}
      <div style={{ marginTop: 4 }}>
        {(q.data?.uses ?? []).slice(0, 3).map((u, i) => (
          <span key={i} className="meta" style={{ marginRight: 6 }}>
            score {u.score.toFixed(2)}
          </span>
        ))}
      </div>
    </li>
  )
}
