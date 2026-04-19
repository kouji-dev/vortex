import * as React from 'react'
import { authorizedFetch } from '~/lib/authorizedFetch'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

interface UsageRow {
  group_key: string
  input_tokens: number
  output_tokens: number
  cached_input_tokens: number
  cost_usd: string
  message_count: number
}

interface UsageSummary {
  start: string
  end: string
  group_by: string
  rows: UsageRow[]
  total_cost_usd: string
  total_messages: number
}

export function UsagePanel() {
  const [summary, setSummary] = React.useState<UsageSummary | null>(null)
  const [groupBy, setGroupBy] = React.useState<'model' | 'user' | 'capability'>('model')
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    setLoading(true)
    setError(null)
    authorizedFetch(`${API_BASE}/api/admin/usage/summary?group_by=${groupBy}`)
      .then((r) => r.json())
      .then(setSummary)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [groupBy])

  return (
    <div>
      <div className="panel-head" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span>Usage &amp; Cost (last 30 days)</span>
        <select
          value={groupBy}
          onChange={(e) => setGroupBy(e.target.value as typeof groupBy)}
          style={{ borderRadius: 3, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--ink)', padding: '3px 8px', fontSize: 11, fontFamily: 'var(--font-mono)' }}
        >
          <option value="model">By model</option>
          <option value="user">By user</option>
          <option value="capability">By capability</option>
        </select>
      </div>

      {error && <p style={{ padding: '8px 14px', fontSize: 12, color: 'var(--red)' }}>{error}</p>}

      {summary && (
        <div className="kpi-row" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
          <div className="kpi">
            <div className="kpi-label">Total cost</div>
            <div className="kpi-value">${parseFloat(summary.total_cost_usd).toFixed(4)}</div>
          </div>
          <div className="kpi">
            <div className="kpi-label">Total messages</div>
            <div className="kpi-value">{summary.total_messages.toLocaleString()}</div>
          </div>
          <div className="kpi">
            <div className="kpi-label">Groups</div>
            <div className="kpi-value">{summary.rows.length}</div>
          </div>
        </div>
      )}

      {loading && <p style={{ padding: '8px 14px', fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}

      {summary && summary.rows.length > 0 && (
        <div>
          {/* header */}
          <div className="audit-row" style={{ gridTemplateColumns: '1fr 80px 100px 100px 80px 100px', background: 'var(--bg-2)', borderBottom: '1px solid var(--line)', fontWeight: 600, fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            <span>Group</span>
            <span style={{ textAlign: 'right' }}>Msgs</span>
            <span style={{ textAlign: 'right' }}>Input tokens</span>
            <span style={{ textAlign: 'right' }}>Output tokens</span>
            <span style={{ textAlign: 'right' }}>Cached</span>
            <span style={{ textAlign: 'right' }}>Cost (USD)</span>
          </div>
          {summary.rows.map((row) => (
            <div key={row.group_key} className="audit-row" style={{ gridTemplateColumns: '1fr 80px 100px 100px 80px 100px' }}>
              <span style={{ color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 200 }}>{row.group_key}</span>
              <span style={{ textAlign: 'right', color: 'var(--ink-2)' }}>{row.message_count.toLocaleString()}</span>
              <span style={{ textAlign: 'right', color: 'var(--ink-2)' }}>{row.input_tokens.toLocaleString()}</span>
              <span style={{ textAlign: 'right', color: 'var(--ink-2)' }}>{row.output_tokens.toLocaleString()}</span>
              <span style={{ textAlign: 'right', color: 'var(--accent)' }}>{row.cached_input_tokens.toLocaleString()}</span>
              <span style={{ textAlign: 'right', color: 'var(--ink)', fontWeight: 600 }}>${parseFloat(row.cost_usd).toFixed(6)}</span>
            </div>
          ))}
        </div>
      )}

      {summary && summary.rows.length === 0 && !loading && (
        <p style={{ padding: '20px 14px', fontSize: 12, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>No usage data for this period.</p>
      )}
    </div>
  )
}
