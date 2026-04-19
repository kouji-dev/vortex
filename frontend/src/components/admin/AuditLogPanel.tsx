import * as React from 'react'
import { authorizedFetch } from '~/lib/authorizedFetch'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

interface AuditEvent {
  id: number
  actor_user_id: number | null
  actor_type: string
  event_type: string
  resource_type: string
  resource_id: string | null
  action: string
  created_at: string
}

interface AuditResponse {
  total: number
  items: AuditEvent[]
}

export function AuditLogPanel() {
  const [data, setData] = React.useState<AuditResponse | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [filterType, setFilterType] = React.useState('')

  const load = React.useCallback(() => {
    setLoading(true)
    setError(null)
    const params = new URLSearchParams({ limit: '100' })
    if (filterType) params.set('event_type', filterType)
    authorizedFetch(`${API_BASE}/api/admin/audit?${params}`)
      .then((r) => r.json())
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [filterType])

  React.useEffect(() => { load() }, [load])

  function exportCsv() {
    window.open(`${API_BASE}/api/admin/audit/export?fmt=csv`, '_blank')
  }

  return (
    <div>
      <div className="panel-head" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <span>
          Audit Log
          {data && <span style={{ marginLeft: 6, fontSize: 11, fontWeight: 400, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>({data.total} events)</span>}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            type="text"
            placeholder="Filter by event type..."
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            style={{ borderRadius: 3, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '3px 8px', fontSize: 11, fontFamily: 'var(--font-mono)', width: 180 }}
          />
          <button onClick={exportCsv} className="btn btn-sm">
            Export CSV
          </button>
        </div>
      </div>

      {error && <p style={{ padding: '8px 14px', fontSize: 12, color: 'var(--red)' }}>{error}</p>}
      {loading && <p style={{ padding: '8px 14px', fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}

      {data && data.items.length > 0 && (
        <div>
          {/* header row */}
          <div className="audit-row" style={{ background: 'var(--bg-2)', borderBottom: '1px solid var(--line)', fontWeight: 600, fontSize: 10, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            <span>Time</span>
            <span>Event</span>
            <span>Resource</span>
            <span>Action</span>
            <span>Actor</span>
          </div>
          {data.items.map((ev) => (
            <div key={ev.id} className="audit-row">
              <span className="ts">{new Date(ev.created_at).toLocaleString()}</span>
              <span style={{ color: 'var(--accent)', fontSize: 11 }}>{ev.event_type}</span>
              <span style={{ color: 'var(--ink-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {ev.resource_type}{ev.resource_id ? ` #${ev.resource_id}` : ''}
              </span>
              <span style={{ color: 'var(--ink-2)', textTransform: 'capitalize' }}>{ev.action}</span>
              <span className="actor" style={{ color: 'var(--ink-3)' }}>
                {ev.actor_user_id ? `user:${ev.actor_user_id}` : ev.actor_type}
              </span>
            </div>
          ))}
        </div>
      )}

      {data && data.items.length === 0 && !loading && (
        <p style={{ padding: '20px 14px', fontSize: 12, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>No audit events.</p>
      )}
    </div>
  )
}
