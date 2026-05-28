/**
 * Q7 — KB chat / playground.
 *
 * Sends a query through `POST /api/kbs/{id}/playground` and displays the
 * retrieved chunks + answer side-by-side. Stores every run as a session so
 * the user can replay it deterministically or promote it to an eval case.
 */
import { useMutation, useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'

import { listEvals, runPlayground, savePlaygroundSessionAsEval } from '~/lib/rag-api'
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

  const evalsQ = useQuery({
    queryKey: ['rag', 'evals', kbId],
    queryFn: () => listEvals(kbId),
  })
  const [savedRecordId, setSavedRecordId] = React.useState<string | null>(null)

  const saveEval = useMutation({
    mutationFn: (testSetId: string) => {
      if (!last?.session_id) throw new Error('No session to save')
      return savePlaygroundSessionAsEval(kbId, last.session_id, testSetId)
    },
    onSuccess: (out) => setSavedRecordId(out.record_id),
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
        <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Retrieved chunks</span>
          {last?.session_id && (
            <SaveAsEvalPicker
              evals={evalsQ.data ?? []}
              loading={evalsQ.isPending}
              onSave={(eid) => saveEval.mutate(eid)}
              saving={saveEval.isPending}
              savedRecordId={savedRecordId}
              error={saveEval.error as Error | null}
            />
          )}
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

function SaveAsEvalPicker({
  evals,
  loading,
  onSave,
  saving,
  savedRecordId,
  error,
}: {
  evals: { id: string; name: string }[]
  loading: boolean
  onSave: (evalId: string) => void
  saving: boolean
  savedRecordId: string | null
  error: Error | null
}) {
  const [open, setOpen] = React.useState(false)
  const [chosen, setChosen] = React.useState<string>('')

  React.useEffect(() => {
    if (!chosen && evals.length > 0) setChosen(evals[0].id)
  }, [evals, chosen])

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        data-testid="rag-playground-save-as-eval"
        style={{ fontSize: 11 }}
      >
        Save as eval
      </button>
    )
  }
  return (
    <div data-testid="rag-playground-save-as-eval-picker" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
      {loading ? (
        <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>Loading test sets…</span>
      ) : evals.length === 0 ? (
        <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>No test sets — create one first.</span>
      ) : (
        <>
          <select
            value={chosen}
            onChange={(e) => setChosen(e.target.value)}
            data-testid="rag-playground-save-as-eval-select"
            style={{ fontSize: 11 }}
          >
            {evals.map((e) => (
              <option key={e.id} value={e.id}>{e.name}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => onSave(chosen)}
            disabled={!chosen || saving}
            data-testid="rag-playground-save-as-eval-submit"
            style={{ fontSize: 11 }}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </>
      )}
      <button
        type="button"
        onClick={() => setOpen(false)}
        data-testid="rag-playground-save-as-eval-cancel"
        style={{ fontSize: 11 }}
      >
        Cancel
      </button>
      {savedRecordId && (
        <span data-testid="rag-playground-save-as-eval-ok" style={{ fontSize: 11, color: 'var(--ok, green)' }}>
          Saved {savedRecordId}
        </span>
      )}
      {error && (
        <span style={{ fontSize: 11, color: 'var(--err, red)' }}>{error.message}</span>
      )}
    </div>
  )
}
