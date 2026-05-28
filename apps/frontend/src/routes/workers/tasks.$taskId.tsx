/**
 * Workers → Task detail → live view.
 *
 * Layout:
 *  ┌────────────────────────────────┬─────────────────┐
 *  │ events stream pane             │ terminal pane   │
 *  │  - agent thoughts              │  (shell output) │
 *  │  - tool_call / tool_result     │                 │
 *  │  - phase_changed / errors      │                 │
 *  ├────────────────────────────────┼─────────────────┤
 *  │ file tree + diff viewer        │ approvals       │
 *  │                                │ artifacts       │
 *  │                                │ controls        │
 *  └────────────────────────────────┴─────────────────┘
 */
import { createFileRoute, Link } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import * as api from '~/lib/workers-api'
import {
  aggregateCostCents,
  buildTerminalLog,
  canCancel,
  canPause,
  canResume,
  eventLabel,
  fileTreeFromEvents,
  formatCents,
  formatTs,
  statusBadgeClass,
} from '~/lib/workers-logic'
import { useWorkerEvents } from '~/lib/workers-sse'
import type { WorkerEvent } from '~/lib/workers-types'

export const Route = createFileRoute('/workers/tasks/$taskId')({
  component: TaskDetailPage,
})

function TaskDetailPage() {
  const { taskId } = Route.useParams()
  const qc = useQueryClient()

  const taskQ = useQuery({
    queryKey: ['workers', 'task', taskId],
    queryFn: () => api.getTask(taskId),
    refetchInterval: 5000,
  })

  const approvalsQ = useQuery({
    queryKey: ['workers', 'task', taskId, 'approvals'],
    queryFn: () => api.listApprovals(taskId),
    refetchInterval: 5000,
  })

  const artifactsQ = useQuery({
    queryKey: ['workers', 'task', taskId, 'artifacts'],
    queryFn: () => api.listArtifacts(taskId),
    refetchInterval: 5000,
  })

  const { events, status: sseStatus } = useWorkerEvents(taskId)

  const terminal = React.useMemo(() => buildTerminalLog(events), [events])
  const files = React.useMemo(() => fileTreeFromEvents(events), [events])
  const cost = React.useMemo(() => aggregateCostCents(events), [events])

  if (taskQ.isPending) {
    return (
      <div className="panel" style={{ padding: 20, fontSize: 12, color: 'var(--ink-3)' }}>
        Loading task…
      </div>
    )
  }
  if (taskQ.isError || !taskQ.data) {
    return (
      <div className="panel" style={{ padding: 20, color: 'var(--red, #c43c3c)' }}>
        Failed to load task.
        <div>
          <Link to="/workers/tasks">← back to tasks</Link>
        </div>
      </div>
    )
  }

  const t = taskQ.data
  return (
    <div data-testid="workers-task-detail">
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 10,
          fontSize: 12,
        }}
      >
        <Link to="/workers/tasks" style={{ color: 'var(--ink-3)' }}>
          ← tasks
        </Link>
        <h2 style={{ margin: 0, fontSize: 16 }}>{t.title}</h2>
        <span className={statusBadgeClass(t.status)}>{t.status}</span>
        <span style={{ color: 'var(--ink-3)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
          {t.repo}
        </span>
        <span style={{ marginLeft: 'auto', color: 'var(--ink-3)', fontSize: 11 }}>
          SSE: {sseStatus}
        </span>
        <span style={{ color: 'var(--ink-3)', fontSize: 11 }}>
          Cost: {formatCents(cost)}
        </span>
      </div>

      <div className="wk-detail-grid">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <EventsPane events={events} />
          <FilesPane files={files} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <TerminalPane log={terminal} />
          <ControlsPane
            taskId={t.id}
            status={t.status}
            onChanged={() => {
              qc.invalidateQueries({ queryKey: ['workers', 'task', taskId] })
              qc.invalidateQueries({ queryKey: ['workers', 'tasks'] })
            }}
          />
          <ApprovalsPane taskId={taskId} approvals={approvalsQ.data ?? []} />
          <ArtifactsPane artifacts={artifactsQ.data ?? []} />
        </div>
      </div>
    </div>
  )
}

function EventsPane({ events }: { events: WorkerEvent[] }) {
  const scrollerRef = React.useRef<HTMLDivElement | null>(null)
  React.useEffect(() => {
    const el = scrollerRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [events.length])
  return (
    <div className="wk-pane">
      <div className="wk-pane-head">
        <span>Agent stream</span>
        <span>{events.length} events</span>
      </div>
      <div
        ref={scrollerRef}
        className="wk-pane-body"
        style={{ maxHeight: 360, overflow: 'auto' }}
        data-testid="wk-events-pane"
      >
        {events.length === 0 ? (
          <div style={{ color: 'var(--ink-3)' }}>Waiting for events…</div>
        ) : (
          events.map((e) => (
            <div key={e.id} className="wk-event-row" data-testid={`wk-event-${e.id}`}>
              <span className="wk-event-ts">{formatTs(e.ts)}</span>
              <span className="wk-event-kind">{eventLabel(e.kind)}</span>
              <span className="wk-event-payload">{summarizeEvent(e)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function summarizeEvent(e: WorkerEvent): string {
  switch (e.kind) {
    case 'agent_thought':
      return String(e.payload?.text ?? '')
    case 'tool_call':
      return `${e.payload?.tool ?? ''} ${JSON.stringify(e.payload?.args ?? e.payload?.cmd ?? {})}`
    case 'tool_result':
      return `${e.payload?.tool ?? ''} ${e.payload?.ok ? 'ok' : 'err'}`
    case 'file_changed':
      return `${e.payload?.action ?? 'edit'} ${e.payload?.path ?? ''}`
    case 'shell_output':
      return String(e.payload?.chunk ?? '').slice(0, 200)
    case 'pr_created':
      return String(e.payload?.url ?? '')
    case 'error':
      return String(e.payload?.error ?? '')
    case 'phase_changed':
      return String(e.payload?.to ?? '')
    case 'user_message':
      return `you: ${String(e.payload?.text ?? '')}`
    case 'cost_update':
      return `cents=${e.payload?.cents}`
    default:
      return JSON.stringify(e.payload)
  }
}

function TerminalPane({ log }: { log: string }) {
  const scrollerRef = React.useRef<HTMLPreElement | null>(null)
  React.useEffect(() => {
    const el = scrollerRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [log])
  return (
    <div className="wk-pane">
      <div className="wk-pane-head">
        <span>Terminal</span>
        <span>{log.length} chars</span>
      </div>
      <pre ref={scrollerRef} className="wk-term" data-testid="wk-terminal-pane">
        {log || '(no shell output yet)'}
      </pre>
    </div>
  )
}

function FilesPane({ files }: { files: { path: string; action: string }[] }) {
  return (
    <div className="wk-pane">
      <div className="wk-pane-head">
        <span>Changed files</span>
        <span>{files.length}</span>
      </div>
      <div className="wk-pane-body" data-testid="wk-files-pane">
        {files.length === 0 ? (
          <div style={{ color: 'var(--ink-3)' }}>No file changes yet.</div>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 16, fontFamily: 'var(--font-mono)', fontSize: 11 }}>
            {files.map((f) => (
              <li key={f.path}>
                <span style={{ color: 'var(--ink-3)', marginRight: 6 }}>[{f.action}]</span>
                {f.path}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function ControlsPane({
  taskId,
  status,
  onChanged,
}: {
  taskId: string
  status: import('~/lib/workers-types').TaskStatus
  onChanged: () => void
}) {
  const [msg, setMsg] = React.useState('')
  const cancelMut = useMutation({ mutationFn: () => api.cancelTask(taskId), onSuccess: onChanged })
  const pauseMut = useMutation({ mutationFn: () => api.pauseTask(taskId), onSuccess: onChanged })
  const resumeMut = useMutation({ mutationFn: () => api.resumeTask(taskId), onSuccess: onChanged })
  const messageMut = useMutation({
    mutationFn: (text: string) => api.sendMessage(taskId, text),
    onSuccess: () => {
      setMsg('')
    },
  })

  return (
    <div className="wk-pane">
      <div className="wk-pane-head">
        <span>Controls</span>
      </div>
      <div className="wk-pane-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            className="btn btn-sm"
            disabled={!canPause(status) || pauseMut.isPending}
            onClick={() => pauseMut.mutate()}
            data-testid="wk-task-pause"
          >
            Pause
          </button>
          <button
            className="btn btn-sm"
            disabled={!canResume(status) || resumeMut.isPending}
            onClick={() => resumeMut.mutate()}
            data-testid="wk-task-resume"
          >
            Resume
          </button>
          <button
            className="btn btn-sm btn-danger"
            disabled={!canCancel(status) || cancelMut.isPending}
            onClick={() => cancelMut.mutate()}
            data-testid="wk-task-cancel"
          >
            Cancel
          </button>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <input
            className="wk-input"
            style={{ flex: 1 }}
            placeholder="Send message to worker…"
            value={msg}
            onChange={(e) => setMsg(e.target.value)}
            data-testid="wk-task-message-input"
          />
          <button
            className="btn btn-sm"
            disabled={!msg.trim() || messageMut.isPending}
            onClick={() => messageMut.mutate(msg.trim())}
            data-testid="wk-task-message-send"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}

function ApprovalsPane({
  taskId,
  approvals,
}: {
  taskId: string
  approvals: import('~/lib/workers-types').WorkerApproval[]
}) {
  const qc = useQueryClient()
  const decideMut = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: 'approve' | 'reject' }) =>
      api.decideApproval(id, decision),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workers', 'task', taskId, 'approvals'] })
      qc.invalidateQueries({ queryKey: ['workers', 'task', taskId] })
    },
  })
  const pending = approvals.filter((a) => !a.decision)
  return (
    <div className="wk-pane">
      <div className="wk-pane-head">
        <span>Approvals</span>
        <span>{pending.length} pending</span>
      </div>
      <div className="wk-pane-body" data-testid="wk-approvals-pane">
        {approvals.length === 0 ? (
          <div style={{ color: 'var(--ink-3)' }}>No approvals requested.</div>
        ) : (
          approvals.map((a) => (
            <div
              key={a.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '4px 0',
                borderBottom: '1px dashed var(--line)',
              }}
              data-testid={`wk-approval-${a.id}`}
            >
              <span style={{ flex: 1 }}>{a.kind}</span>
              {a.decision ? (
                <span style={{ color: 'var(--ink-3)', fontSize: 11 }}>
                  {a.decision} by {a.decided_by ?? '?'}
                </span>
              ) : (
                <>
                  <button
                    className="btn btn-sm"
                    onClick={() => decideMut.mutate({ id: a.id, decision: 'approve' })}
                  >
                    Approve
                  </button>
                  <button
                    className="btn btn-sm btn-danger"
                    onClick={() => decideMut.mutate({ id: a.id, decision: 'reject' })}
                  >
                    Reject
                  </button>
                </>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function ArtifactsPane({
  artifacts,
}: {
  artifacts: import('~/lib/workers-types').WorkerArtifact[]
}) {
  return (
    <div className="wk-pane">
      <div className="wk-pane-head">
        <span>Artifacts</span>
        <span>{artifacts.length}</span>
      </div>
      <div className="wk-pane-body" data-testid="wk-artifacts-pane">
        {artifacts.length === 0 ? (
          <div style={{ color: 'var(--ink-3)' }}>No artifacts yet.</div>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11 }}>
            {artifacts.map((a) => (
              <li key={a.id} style={{ marginBottom: 4 }}>
                <span style={{ color: 'var(--ink-3)', marginRight: 4 }}>[{a.kind}]</span>
                {a.kind === 'pr_url' || a.ref.startsWith('http') ? (
                  <a href={a.ref} target="_blank" rel="noreferrer">
                    {a.ref}
                  </a>
                ) : (
                  <span style={{ fontFamily: 'var(--font-mono)' }}>{a.ref}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
