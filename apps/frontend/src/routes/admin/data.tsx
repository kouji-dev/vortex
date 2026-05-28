import { createFileRoute } from '@tanstack/react-router'
import { useMutation, useQuery } from '@tanstack/react-query'
import * as React from 'react'
import {
  fetchDataDelete,
  fetchDataExport,
  requestDataDelete,
  requestDataExport,
} from '~/lib/admin-api'
import {
  DELETE_CONFIRMATION_PHRASE,
  deleteConfirmed,
  isTerminal,
  jobStateClass,
  summarizeDelete,
  summarizeExport,
} from '~/lib/data-job-state'

export const Route = createFileRoute('/admin/data')({
  component: DataPage,
})

function DataPage() {
  const [exportJobId, setExportJobId] = React.useState<string | null>(null)
  const [deleteJobId, setDeleteJobId] = React.useState<string | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = React.useState(false)

  const requestExport = useMutation({
    mutationFn: requestDataExport,
    onSuccess: (job) => setExportJobId(job.id),
  })

  const requestDelete = useMutation({
    mutationFn: requestDataDelete,
    onSuccess: (job) => {
      setDeleteJobId(job.id)
      setShowDeleteConfirm(false)
    },
  })

  return (
    <div className="panel" data-testid="admin-data">
      <div className="panel-head">
        <span>Data</span>
      </div>
      <div className="panel-body" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 24 }}>
        <ExportSection
          jobId={exportJobId}
          requesting={requestExport.isPending}
          error={requestExport.error?.message ?? null}
          onRequest={() => requestExport.mutate()}
        />

        <DeleteSection
          jobId={deleteJobId}
          requesting={requestDelete.isPending}
          error={requestDelete.error?.message ?? null}
          showConfirm={showDeleteConfirm}
          onShowConfirm={() => setShowDeleteConfirm(true)}
          onCancelConfirm={() => setShowDeleteConfirm(false)}
          onConfirm={() => requestDelete.mutate({ scope: { subject: 'org' } })}
        />
      </div>
    </div>
  )
}

function ExportSection({
  jobId,
  requesting,
  error,
  onRequest,
}: {
  jobId: string | null
  requesting: boolean
  error: string | null
  onRequest: () => void
}) {
  return (
    <section data-testid="admin-data-export">
      <h3 style={{ fontSize: 12, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
        Export org data (GDPR art. 15)
      </h3>
      <p style={{ fontSize: 12, color: 'var(--ink-2)', marginBottom: 12 }}>
        Bundles every row in this org into a downloadable zip. The link is emailed when ready, and you can also fetch it below.
      </p>
      <button
        className="btn btn-primary"
        onClick={onRequest}
        disabled={requesting}
        data-testid="admin-data-export-request"
      >
        {requesting ? 'Requesting…' : 'Request export'}
      </button>
      {error && <p style={{ fontSize: 11, color: 'var(--red)', marginTop: 8 }}>{error}</p>}
      {jobId && <ExportJobPoller jobId={jobId} />}
    </section>
  )
}

function ExportJobPoller({ jobId }: { jobId: string }) {
  const q = useQuery({
    queryKey: ['admin', 'data-export', jobId],
    queryFn: () => fetchDataExport(jobId),
    refetchInterval: (query) => {
      const data = query.state.data
      if (data && isTerminal(data.status)) return false
      return 3000
    },
  })

  if (q.isPending) return <p style={{ marginTop: 12, fontSize: 12, color: 'var(--ink-3)' }}>Tracking job…</p>
  if (q.error) return <p style={{ marginTop: 12, fontSize: 12, color: 'var(--red)' }}>{(q.error as Error).message}</p>
  if (!q.data) return null

  const s = summarizeExport(q.data)
  return (
    <div
      style={{ marginTop: 12, padding: 12, border: '1px solid var(--line)', borderRadius: 4, background: 'var(--bg-2)' }}
      data-testid="admin-data-export-status"
    >
      <Kv label="Job" value={s.id} mono />
      <Kv label="Status" value={s.status} color={jobStateClass(s.status) === 'failed' ? 'var(--red)' : undefined} />
      <Kv label="Requested" value={new Date(s.requestedAt).toLocaleString()} />
      {s.completedAt && <Kv label="Completed" value={new Date(s.completedAt).toLocaleString()} />}
      {s.resultUrl && (
        <a
          className="btn btn-primary"
          style={{ marginTop: 8 }}
          href={s.resultUrl}
          target="_blank"
          rel="noopener"
          data-testid="admin-data-export-download"
        >
          Download zip
        </a>
      )}
    </div>
  )
}

function DeleteSection({
  jobId,
  requesting,
  error,
  showConfirm,
  onShowConfirm,
  onCancelConfirm,
  onConfirm,
}: {
  jobId: string | null
  requesting: boolean
  error: string | null
  showConfirm: boolean
  onShowConfirm: () => void
  onCancelConfirm: () => void
  onConfirm: () => void
}) {
  return (
    <section data-testid="admin-data-delete">
      <h3 style={{ fontSize: 12, color: 'var(--red)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
        Delete org data (GDPR art. 17)
      </h3>
      <p style={{ fontSize: 12, color: 'var(--ink-2)', marginBottom: 12 }}>
        Schedules irreversible deletion of every row associated with this organisation across all modules. An audit event is emitted.
      </p>
      <button
        className="btn"
        style={{ color: 'var(--red)', borderColor: 'var(--red)' }}
        onClick={onShowConfirm}
        data-testid="admin-data-delete-request"
      >
        Request deletion
      </button>
      {error && <p style={{ fontSize: 11, color: 'var(--red)', marginTop: 8 }}>{error}</p>}
      {jobId && <DeleteJobPoller jobId={jobId} />}

      {showConfirm && (
        <DeleteConfirmDialog
          requesting={requesting}
          onCancel={onCancelConfirm}
          onConfirm={onConfirm}
        />
      )}
    </section>
  )
}

function DeleteJobPoller({ jobId }: { jobId: string }) {
  const q = useQuery({
    queryKey: ['admin', 'data-delete', jobId],
    queryFn: () => fetchDataDelete(jobId),
    refetchInterval: (query) => {
      const data = query.state.data
      if (data && isTerminal(data.status)) return false
      return 3000
    },
  })

  if (q.isPending) return <p style={{ marginTop: 12, fontSize: 12, color: 'var(--ink-3)' }}>Tracking job…</p>
  if (q.error) return <p style={{ marginTop: 12, fontSize: 12, color: 'var(--red)' }}>{(q.error as Error).message}</p>
  if (!q.data) return null

  const s = summarizeDelete(q.data)
  return (
    <div
      style={{ marginTop: 12, padding: 12, border: '1px solid var(--line)', borderRadius: 4, background: 'var(--bg-2)' }}
      data-testid="admin-data-delete-status"
    >
      <Kv label="Job" value={s.id} mono />
      <Kv label="Status" value={s.status} color={jobStateClass(s.status) === 'failed' ? 'var(--red)' : undefined} />
      <Kv label="Scope" value={s.scopeLabel ?? '—'} />
      <Kv label="Requested" value={new Date(s.requestedAt).toLocaleString()} />
      {s.completedAt && <Kv label="Completed" value={new Date(s.completedAt).toLocaleString()} />}
    </div>
  )
}

function DeleteConfirmDialog({
  requesting,
  onCancel,
  onConfirm,
}: {
  requesting: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const [typed, setTyped] = React.useState('')
  const confirmed = deleteConfirmed(typed)

  return (
    <div
      role="dialog"
      aria-modal="true"
      data-testid="admin-data-delete-dialog"
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }}
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ background: 'var(--bg)', border: '1px solid var(--red)', borderRadius: 8, padding: 20, width: '90%', maxWidth: 560 }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--red)' }}>Confirm deletion</h3>
          <button type="button" onClick={onCancel} className="btn btn-sm" aria-label="Close">✕</button>
        </div>
        <p style={{ fontSize: 12, color: 'var(--ink-2)', marginBottom: 12 }}>
          You are about to permanently delete <strong>all data</strong> for this organisation across every module. This cannot be undone.
        </p>
        <p style={{ fontSize: 12, color: 'var(--ink-2)', marginBottom: 12 }}>
          Type <code style={{ background: 'var(--bg-2)', padding: '2px 6px', borderRadius: 3 }}>{DELETE_CONFIRMATION_PHRASE}</code> to confirm.
        </p>
        <input
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder={DELETE_CONFIRMATION_PHRASE}
          data-testid="admin-data-delete-confirm-input"
          style={{ width: '100%', borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '8px 10px', fontSize: 13, marginBottom: 16 }}
        />
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="btn"
            style={{ color: 'var(--red)', borderColor: 'var(--red)' }}
            onClick={onConfirm}
            disabled={!confirmed || requesting}
            data-testid="admin-data-delete-confirm"
          >
            {requesting ? 'Requesting…' : 'Delete everything'}
          </button>
          <button type="button" className="btn btn-sm" onClick={onCancel}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

function Kv({
  label,
  value,
  color,
  mono,
}: {
  label: string
  value: string
  color?: string
  mono?: boolean
}) {
  return (
    <div style={{ display: 'flex', gap: 8, fontSize: 12, marginBottom: 4 }}>
      <span className="meta" style={{ minWidth: 90, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: 10 }}>{label}</span>
      <span style={{ color: color ?? 'var(--ink)', fontFamily: mono ? 'var(--font-mono)' : undefined }}>{value}</span>
    </div>
  )
}
