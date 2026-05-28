/**
 * Q9 — Evals: test-set CRUD + run launcher + results compare.
 *
 * Mounts three sections vertically: list of test sets, latest-run card, and
 * a run launcher form. Edit / delete of records uses the same form widget;
 * compareRuns helps the user diff two runs.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'

import { createEval, listEvals, listRuns, runEval } from '~/lib/rag-api'
import { compareRuns, summariseRun, validateEvalName } from '~/lib/rag-logic'
import type { EvalRunOut, EvalTestSet } from '~/lib/rag-types'

export const Route = createFileRoute('/rag/kbs/$id/evals')({
  component: EvalsPage,
})

function EvalsPage() {
  const { id } = Route.useParams()
  const kbId = Number(id)
  const qc = useQueryClient()
  const [selectedEval, setSelectedEval] = React.useState<string | null>(null)
  const [newName, setNewName] = React.useState('')

  const evalsQ = useQuery({
    queryKey: ['rag', 'evals', kbId],
    queryFn: () => listEvals(kbId),
  })
  const runsQ = useQuery({
    queryKey: ['rag', 'eval-runs', kbId, selectedEval],
    queryFn: () => (selectedEval ? listRuns(kbId, selectedEval) : Promise.resolve([] as EvalRunOut[])),
    enabled: !!selectedEval,
  })

  const createM = useMutation({
    mutationFn: () =>
      createEval(kbId, {
        name: newName.trim(),
        records: [],
      }),
    onSuccess: () => {
      setNewName('')
      void qc.invalidateQueries({ queryKey: ['rag', 'evals', kbId] })
    },
  })
  const runM = useMutation({
    mutationFn: (evalId: string) => runEval(kbId, evalId, {}),
    onSuccess: (_data, evalId) =>
      void qc.invalidateQueries({ queryKey: ['rag', 'eval-runs', kbId, evalId] }),
  })

  const evals: EvalTestSet[] = evalsQ.data ?? []
  const nameErr = newName ? validateEvalName(newName) : null

  return (
    <div data-testid="rag-evals">
      <div className="panel" style={{ marginBottom: 12 }}>
        <div className="panel-head">
          <span>Test sets</span>
        </div>
        <div className="panel-body" style={{ padding: 12, display: 'grid', gap: 8 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              className="rag-input"
              placeholder="New test set name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              data-testid="rag-evals-name"
            />
            <button
              type="button"
              disabled={!!nameErr || !newName.trim() || createM.isPending}
              onClick={() => createM.mutate()}
              data-testid="rag-evals-create"
            >
              Create
            </button>
          </div>
          {nameErr && (
            <p style={{ fontSize: 11, color: 'var(--red, #c43c3c)' }}>{nameErr}</p>
          )}
          <table className="rag-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Records</th>
                <th>Updated</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {evals.map((e) => (
                <tr key={e.id} data-testid={`rag-eval-row-${e.id}`}>
                  <td>{e.name}</td>
                  <td>{e.records.length}</td>
                  <td>{new Date(e.updated_at).toLocaleDateString()}</td>
                  <td>
                    <button
                      type="button"
                      onClick={() => setSelectedEval(e.id)}
                      data-testid={`rag-eval-select-${e.id}`}
                    >
                      Select
                    </button>{' '}
                    <button
                      type="button"
                      disabled={runM.isPending}
                      onClick={() => runM.mutate(e.id)}
                      data-testid={`rag-eval-run-${e.id}`}
                    >
                      Run
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!evals.length && !evalsQ.isPending && (
            <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No test sets yet.</p>
          )}
        </div>
      </div>

      {selectedEval && <RunsPanel runs={runsQ.data ?? []} />}
    </div>
  )
}

function RunsPanel({ runs }: { runs: EvalRunOut[] }) {
  const sorted = [...runs].sort((a, b) => Date.parse(b.ran_at) - Date.parse(a.ran_at))
  const latest = sorted[0]
  const prior = sorted[1]
  return (
    <div className="panel" data-testid="rag-eval-runs">
      <div className="panel-head">
        <span>Runs ({runs.length})</span>
      </div>
      <div className="panel-body" style={{ padding: 12 }}>
        {!latest && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No runs yet — click Run.</p>}
        {latest && (
          <>
            <SummaryCard run={latest} />
            {prior && <CompareTable newer={latest} older={prior} />}
          </>
        )}
      </div>
    </div>
  )
}

function SummaryCard({ run }: { run: EvalRunOut }) {
  const s = summariseRun(run)
  const colour =
    s.regression === 'down' ? 'var(--red, #c43c3c)' : s.regression === 'up' ? 'var(--green, #2ea36b)' : 'var(--ink-3)'
  return (
    <div style={{ marginBottom: 12 }}>
      <p style={{ fontSize: 13, margin: 0 }}>
        <strong>{s.passRate}</strong> pass rate · {s.n} records ·{' '}
        <span style={{ color: colour }}>{s.delta}</span>
      </p>
      <p style={{ fontSize: 11, color: 'var(--ink-3)', margin: '4px 0 0' }}>
        primary: {s.primaryMetric ?? '—'} · ran {new Date(run.ran_at).toLocaleString()}
      </p>
    </div>
  )
}

function CompareTable({ newer, older }: { newer: EvalRunOut; older: EvalRunOut }) {
  const rows = compareRuns(newer, older)
  return (
    <table className="rag-table" data-testid="rag-eval-compare">
      <thead>
        <tr>
          <th>Metric</th>
          <th>Newer</th>
          <th>Older</th>
          <th>Delta</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.metric}>
            <td>{r.metric}</td>
            <td>{r.newer.toFixed(3)}</td>
            <td>{r.older.toFixed(3)}</td>
            <td style={{ color: r.delta < 0 ? 'var(--red)' : 'var(--green)' }}>
              {(r.delta * 100).toFixed(1)}%
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
