/**
 * Workers → Worker detail → two-pane (interactive mode).
 *
 *  ┌──────────────────────────────┬──────────────────────────────┐
 *  │ LEFT — interactive agent chat │ RIGHT — run-scoped panel      │
 *  │  worker chat thread           │  highlighted diff +           │
 *  │  + message composer (= a run) │  changed-files for selected   │
 *  │                               │  run; switch runs             │
 *  └──────────────────────────────┴──────────────────────────────┘
 *
 * Agent execution is stubbed on the backend; sending a message creates a run
 * (status running) but no agent output streams yet. The UI is wired against
 * the real instance API.
 */
import { createFileRoute, Link } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import * as api from '~/lib/workers-api'
import {
  formatTs,
  runStatusBadgeClass,
  workerStateBadgeClass,
} from '~/lib/workers-logic'
import type { InstanceRun } from '~/lib/workers-types'

export const Route = createFileRoute('/workers/instances/$workerId')({
  component: WorkerDetailPage,
})

function WorkerDetailPage() {
  const { workerId } = Route.useParams()
  const qc = useQueryClient()
  const [selectedRunId, setSelectedRunId] = React.useState<string | null>(null)

  const workerQ = useQuery({
    queryKey: ['workers', 'instance', workerId],
    queryFn: () => api.getWorker(workerId),
    refetchInterval: 5000,
  })

  const messagesQ = useQuery({
    queryKey: ['workers', 'instance', workerId, 'messages'],
    queryFn: () => api.listWorkerMessages(workerId),
    refetchInterval: 3000,
  })

  const runsQ = useQuery({
    queryKey: ['workers', 'instance', workerId, 'runs'],
    queryFn: () => api.listWorkerRuns(workerId),
    refetchInterval: 3000,
  })

  // Auto-select the latest run when runs load and none is selected.
  React.useEffect(() => {
    const runs = runsQ.data
    if (runs && runs.length > 0 && selectedRunId === null) {
      setSelectedRunId(runs[runs.length - 1].id)
    }
  }, [runsQ.data, selectedRunId])

  if (workerQ.isPending) {
    return (
      <div className="panel" style={{ padding: 20, fontSize: 12, color: 'var(--ink-3)' }}>
        Loading worker…
      </div>
    )
  }
  if (workerQ.isError || !workerQ.data) {
    return (
      <div className="panel" style={{ padding: 20, color: 'var(--red, #c43c3c)' }}>
        Failed to load worker.
        <div>
          <Link to="/workers/instances">← back to workers</Link>
        </div>
      </div>
    )
  }

  const w = workerQ.data
  return (
    <div data-testid="workers-instance-detail">
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 10,
          fontSize: 12,
        }}
      >
        <Link to="/workers/instances" style={{ color: 'var(--ink-3)' }}>
          ← workers
        </Link>
        <h2 style={{ margin: 0, fontSize: 16 }}>{w.name}</h2>
        <span className={workerStateBadgeClass(w.state)} data-testid="wk-instance-detail-state">
          {w.state}
        </span>
        <span style={{ color: 'var(--ink-3)', fontSize: 11 }}>{w.mode}</span>
        <span style={{ color: 'var(--ink-3)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
          {w.model} · {w.runtime}
        </span>
        <span
          style={{ marginLeft: 'auto', color: 'var(--ink-3)', fontFamily: 'var(--font-mono)', fontSize: 11 }}
        >
          {w.repo_url ?? '—'}
        </span>
      </div>

      <div
        className="wk-instance-grid"
        data-testid="wk-instance-grid"
        style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, alignItems: 'start' }}
      >
        <ChatPane
          workerId={workerId}
          messages={messagesQ.data ?? []}
          disabled={w.state === 'stopped'}
          onSent={() => {
            qc.invalidateQueries({ queryKey: ['workers', 'instance', workerId, 'messages'] })
            qc.invalidateQueries({ queryKey: ['workers', 'instance', workerId, 'runs'] })
            qc.invalidateQueries({ queryKey: ['workers', 'instance', workerId] })
          }}
        />
        <RunPanel
          runs={runsQ.data ?? []}
          selectedRunId={selectedRunId}
          onSelectRun={setSelectedRunId}
        />
      </div>
    </div>
  )
}

function ChatPane({
  workerId,
  messages,
  disabled,
  onSent,
}: {
  workerId: string
  messages: import('~/lib/workers-types').WorkerChatMessage[]
  disabled: boolean
  onSent: () => void
}) {
  const [text, setText] = React.useState('')
  const scrollerRef = React.useRef<HTMLDivElement | null>(null)
  React.useEffect(() => {
    const el = scrollerRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages.length])

  const sendMut = useMutation({
    mutationFn: (t: string) => api.messageWorker(workerId, t),
    onSuccess: () => {
      setText('')
      onSent()
    },
  })

  return (
    <div className="wk-pane" data-testid="wk-instance-chat">
      <div className="wk-pane-head">
        <span>Agent chat</span>
        <span>{messages.length} messages</span>
      </div>
      <div
        ref={scrollerRef}
        className="wk-pane-body"
        style={{ maxHeight: 420, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}
      >
        {messages.length === 0 ? (
          <div style={{ color: 'var(--ink-3)' }}>
            No messages yet. Send one to start a run.
          </div>
        ) : (
          messages.map((m) => (
            <div key={m.id} data-testid={`wk-instance-msg-${m.id}`} className={`wk-chat-msg wk-chat-${m.role}`}>
              <span className="wk-chat-role">{m.role}</span>
              <span style={{ whiteSpace: 'pre-wrap' }}>{m.content}</span>
            </div>
          ))
        )}
      </div>
      <div style={{ display: 'flex', gap: 6, padding: '8px 12px', borderTop: '1px solid var(--line)' }}>
        <input
          className="wk-input"
          style={{ flex: 1 }}
          placeholder={disabled ? 'Worker stopped' : 'Message the agent (= a run)…'}
          value={text}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && text.trim() && !disabled) sendMut.mutate(text.trim())
          }}
          data-testid="wk-instance-chat-input"
        />
        <button
          className="btn btn-sm btn-primary"
          disabled={!text.trim() || disabled || sendMut.isPending}
          onClick={() => sendMut.mutate(text.trim())}
          data-testid="wk-instance-chat-send"
        >
          Send
        </button>
      </div>
      {sendMut.error && (
        <div style={{ color: 'var(--red, #c43c3c)', fontSize: 11, padding: '0 12px 8px' }}>
          {(sendMut.error as Error).message}
        </div>
      )}
      <WkInstanceStyles />
    </div>
  )
}

function RunPanel({
  runs,
  selectedRunId,
  onSelectRun,
}: {
  runs: InstanceRun[]
  selectedRunId: string | null
  onSelectRun: (id: string) => void
}) {
  const changesQ = useQuery({
    queryKey: ['workers', 'run', selectedRunId, 'changes'],
    queryFn: () => api.listRunChanges(selectedRunId as string),
    enabled: !!selectedRunId,
    refetchInterval: 3000,
  })

  return (
    <div className="wk-pane" data-testid="wk-instance-run-panel">
      <div className="wk-pane-head">
        <span>Runs</span>
        <span>{runs.length}</span>
      </div>
      <div style={{ display: 'flex', gap: 6, padding: '8px 12px', flexWrap: 'wrap' }}>
        {runs.length === 0 ? (
          <span style={{ color: 'var(--ink-3)', fontSize: 12 }}>No runs yet.</span>
        ) : (
          runs.map((r) => (
            <button
              key={r.id}
              className={`btn btn-sm${r.id === selectedRunId ? ' btn-primary' : ''}`}
              onClick={() => onSelectRun(r.id)}
              data-testid={`wk-instance-run-tab-${r.id}`}
            >
              #{r.seq_no}
              <span className={runStatusBadgeClass(r.status)} style={{ marginLeft: 6 }}>
                {r.status}
              </span>
            </button>
          ))
        )}
      </div>

      <div className="wk-pane-body" style={{ borderTop: '1px solid var(--line)' }}>
        <div style={{ fontSize: 11, color: 'var(--ink-3)', marginBottom: 6 }}>
          Changed files
        </div>
        {!selectedRunId ? (
          <div style={{ color: 'var(--ink-3)' }}>Select a run.</div>
        ) : changesQ.isPending ? (
          <div style={{ color: 'var(--ink-3)' }}>Loading changes…</div>
        ) : (changesQ.data ?? []).length === 0 ? (
          <div style={{ color: 'var(--ink-3)' }} data-testid="wk-instance-run-nochanges">
            No file changes for this run.
          </div>
        ) : (
          <div data-testid="wk-instance-run-changes">
            {(changesQ.data ?? []).map((c) => (
              <div key={c.id} className="wk-change-row" data-testid={`wk-instance-change-${c.id}`}>
                <span style={{ color: 'var(--ink-3)', marginRight: 6 }}>[{c.change_kind}]</span>
                <span style={{ fontFamily: 'var(--font-mono)' }}>{c.file_path}</span>
                <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 10 }}>
                  <span style={{ color: 'var(--green, #2e7d32)' }}>+{c.additions}</span>{' '}
                  <span style={{ color: 'var(--red, #c43c3c)' }}>-{c.deletions}</span>
                </span>
                {c.diff_ref && c.diff_ref.includes('\n') && (
                  <pre className="wk-diff">{c.diff_ref}</pre>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function WkInstanceStyles() {
  return (
    <style>{`
      .wk-chat-msg { display: flex; flex-direction: column; gap: 2px; font-size: 12px; }
      .wk-chat-role { font-size: 10px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.04em; }
      .wk-chat-user { align-items: flex-end; }
      .wk-chat-user .wk-chat-role { color: var(--ink-2); }
      .wk-change-row {
        display: flex; align-items: center; flex-wrap: wrap;
        padding: 4px 0; font-size: 11px; border-bottom: 1px dashed var(--line);
      }
      .wk-diff {
        flex-basis: 100%; background: #0b0b0b; color: #d8d8d8;
        font-family: var(--font-mono); font-size: 10px; padding: 8px;
        border-radius: 4px; margin: 6px 0 0; white-space: pre-wrap; overflow: auto;
      }
    `}</style>
  )
}
