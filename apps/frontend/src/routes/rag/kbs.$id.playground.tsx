/**
 * Q7 — KB chat / playground.
 *
 * Sends a query through `POST /api/kbs/{id}/playground` and displays the
 * retrieved chunks + answer side-by-side. Stores every run as a session so
 * the user can replay it deterministically or promote it to an eval case.
 */
import { useMutation } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'

import { runPlayground } from '~/lib/rag-api'
import type { PlaygroundResponse } from '~/lib/rag-types'

export const Route = createFileRoute('/rag/kbs/$id/playground')({
  component: PlaygroundPage,
})

function PlaygroundPage() {
  const { id } = Route.useParams()
  const kbId = Number(id)
  const [query, setQuery] = React.useState('')
  const [topK, setTopK] = React.useState(5)
  const [rerank, setRerank] = React.useState(true)
  const [last, setLast] = React.useState<PlaygroundResponse | null>(null)

  const m = useMutation({
    mutationFn: () =>
      runPlayground(kbId, {
        query,
        settings: { top_k: topK, rerank, min_score: 0 },
        save: true,
      }),
    onSuccess: (r) => setLast(r),
  })

  return (
    <div data-testid="rag-playground" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <div className="panel">
        <div className="panel-head">
          <span>Ask the KB</span>
        </div>
        <div className="panel-body" style={{ padding: 12, display: 'grid', gap: 8 }}>
          <textarea
            className="rag-textarea"
            rows={6}
            placeholder="Ask a question…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            data-testid="rag-playground-query"
          />
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12 }}>
            <label>
              top_k
              <input
                type="number"
                min={1}
                max={50}
                className="rag-input"
                style={{ width: 60, marginLeft: 6 }}
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
                data-testid="rag-playground-topk"
              />
            </label>
            <label>
              <input
                type="checkbox"
                checked={rerank}
                onChange={(e) => setRerank(e.target.checked)}
                data-testid="rag-playground-rerank"
              />{' '}
              rerank
            </label>
          </div>
          <button
            type="button"
            disabled={!query.trim() || m.isPending}
            onClick={() => m.mutate()}
            data-testid="rag-playground-run"
          >
            {m.isPending ? 'Running…' : 'Run'}
          </button>
          {m.error && (
            <p style={{ fontSize: 12, color: 'var(--red, #c43c3c)' }}>{(m.error as Error).message}</p>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <span>Retrieved chunks</span>
        </div>
        <div className="panel-body" style={{ padding: 12 }}>
          {last?.retrieved.length ? (
            <ol style={{ paddingLeft: 18 }}>
              {last.retrieved.map((c) => (
                <li
                  key={c.chunk_id}
                  style={{ fontSize: 12, marginBottom: 8 }}
                  data-testid={`rag-playground-chunk-${c.chunk_id}`}
                >
                  <div style={{ color: 'var(--ink-3)', fontFamily: 'var(--font-mono)', fontSize: 10 }}>
                    score {c.score.toFixed(3)} · doc {c.document_id}
                  </div>
                  <div>{c.text.slice(0, 280)}{c.text.length > 280 ? '…' : ''}</div>
                </li>
              ))}
            </ol>
          ) : (
            <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Run a query to see retrieved chunks.</p>
          )}
        </div>
      </div>
    </div>
  )
}
