// apps/frontend/src/routes/gateway/traces.tsx
// Gateway → Traces (J7): table + drawer + replay (with overrides).
import { Select } from '~/components/ui/select'
import { createFileRoute } from '@tanstack/react-router'
import * as React from 'react'
import { authorizedFetch } from '~/lib/authorizedFetch'
import {
  buildTraceQuery,
  formatCents,
  formatMs,
  traceStatusBadge,
  type TraceFilters,
} from '~/lib/traces-logic'
import type { ModelInfo, RoutingPolicy, TraceDetail, TraceRow, TraceStatus } from '~/lib/gateway-types'

export const Route = createFileRoute('/gateway/traces')({
  component: TracesPage,
})

const API_BASE = import.meta.env.VITE_API_URL ?? ''

function TracesPage() {
  const [filters, setFilters] = React.useState<TraceFilters>({ status: 'all' })
  const [rows, setRows] = React.useState<TraceRow[]>([])
  const [loading, setLoading] = React.useState(false)
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const [models, setModels] = React.useState<ModelInfo[]>([])
  const [policies, setPolicies] = React.useState<RoutingPolicy[]>([])

  React.useEffect(() => {
    authorizedFetch(`${API_BASE}/api/v1/models`)
      .then((r) => r.json())
      .then((d) => Array.isArray(d?.data) && setModels(d.data))
      .catch(() => null)
    authorizedFetch(`${API_BASE}/api/v1/gateway/routing-policies`)
      .then((r) => r.json())
      .then((d) => Array.isArray(d) && setPolicies(d))
      .catch(() => null)
  }, [])

  const reload = React.useCallback(() => {
    setLoading(true)
    const qs = buildTraceQuery(filters)
    authorizedFetch(`${API_BASE}/api/v1/gateway/traces${qs ? '?' + qs : ''}`)
      .then((r) => r.json())
      .then((d) => Array.isArray(d?.rows) ? setRows(d.rows) : setRows([]))
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }, [filters])

  React.useEffect(() => {
    reload()
  }, [reload])

  return (
    <div className="main-inner" data-testid="gateway-traces">
      <div className="screen-head">
        <div>
          <h1>Traces</h1>
          <div className="sub">Per-request audit · latency · cost · replay</div>
        </div>
      </div>

      <FiltersBar filters={filters} onChange={setFilters} />

      <div className="panel">
        <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>{loading ? 'Loading…' : `${rows.length} traces`}</span>
          <button className="btn btn-sm" onClick={reload}>Refresh</button>
        </div>
        <div style={{ overflow: 'auto' }}>
          <table className="tbl" style={{ width: '100%', fontSize: 11 }}>
            <thead>
              <tr>
                <th>Time</th>
                <th>Route</th>
                <th>Model</th>
                <th>Provider</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Latency</th>
                <th style={{ textAlign: 'right' }}>Tokens</th>
                <th style={{ textAlign: 'right' }}>Cost</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-3)' }}>
                    {new Date(r.ts).toLocaleTimeString()}
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{r.route}</td>
                  <td>{r.model_used ?? r.model_requested}</td>
                  <td>{r.provider ?? '—'}</td>
                  <td><span className={traceStatusBadge(r.status)}>{r.status}</span></td>
                  <td style={{ textAlign: 'right' }}>{formatMs(r.latency_ms)}</td>
                  <td style={{ textAlign: 'right' }}>
                    {(r.tokens_in ?? 0) + (r.tokens_out ?? 0)}
                    {r.cache_hit && <span style={{ color: 'var(--accent)', marginLeft: 4 }}>•cache</span>}
                  </td>
                  <td style={{ textAlign: 'right' }}>{formatCents(r.cost_cents)}</td>
                  <td>
                    <button className="btn btn-sm" onClick={() => setSelectedId(r.id)} data-testid={`view-${r.id}`}>
                      View
                    </button>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && !loading && (
                <tr><td colSpan={9} style={{ padding: 24, textAlign: 'center', color: 'var(--ink-3)' }}>No traces.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selectedId && (
        <TraceDrawer
          traceId={selectedId}
          models={models}
          policies={policies}
          onClose={() => setSelectedId(null)}
          onReplayed={() => {
            setSelectedId(null)
            reload()
          }}
        />
      )}
    </div>
  )
}

function FiltersBar({ filters, onChange }: { filters: TraceFilters; onChange: (f: TraceFilters) => void }) {
  const STATUSES: (TraceStatus | 'all')[] = ['all', 'ok', 'error', 'blocked', 'rate_limited', 'budget_exhausted']
  return (
    <div className="panel" style={{ marginBottom: 12 }}>
      <div className="panel-body" style={{ display: 'flex', gap: 8, padding: 12, flexWrap: 'wrap' }}>
        <input
          placeholder="Search…"
          value={filters.search ?? ''}
          onChange={(e) => onChange({ ...filters, search: e.target.value })}
          style={{ fontSize: 11, padding: 4, border: '1px solid var(--line)', borderRadius: 3, background: 'var(--bg)', color: 'var(--ink)' }}
        />
        <input
          placeholder="Model"
          value={filters.model ?? ''}
          onChange={(e) => onChange({ ...filters, model: e.target.value })}
          style={{ fontSize: 11, padding: 4, border: '1px solid var(--line)', borderRadius: 3, background: 'var(--bg)', color: 'var(--ink)' }}
        />
        <input
          placeholder="Provider"
          value={filters.provider ?? ''}
          onChange={(e) => onChange({ ...filters, provider: e.target.value })}
          style={{ fontSize: 11, padding: 4, border: '1px solid var(--line)', borderRadius: 3, background: 'var(--bg)', color: 'var(--ink)' }}
        />
        <Select
          value={filters.status ?? 'all'}
          onChange={(e) => onChange({ ...filters, status: e.target.value as TraceStatus | 'all' })}
        size="sm"
        inline
        >
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </Select>
      </div>
    </div>
  )
}

function TraceDrawer({
  traceId,
  models,
  policies,
  onClose,
  onReplayed,
}: {
  traceId: string
  models: ModelInfo[]
  policies: RoutingPolicy[]
  onClose: () => void
  onReplayed: () => void
}) {
  const [detail, setDetail] = React.useState<TraceDetail | null>(null)
  const [overrideModel, setOverrideModel] = React.useState<string>('')
  const [overridePolicy, setOverridePolicy] = React.useState<string>('')
  const [replaying, setReplaying] = React.useState(false)
  const [err, setErr] = React.useState<string | null>(null)

  React.useEffect(() => {
    authorizedFetch(`${API_BASE}/api/v1/gateway/traces/${traceId}`)
      .then((r) => r.json())
      .then(setDetail)
      .catch((e) => setErr(e.message))
  }, [traceId])

  async function replay() {
    setReplaying(true)
    setErr(null)
    try {
      const body: Record<string, string> = {}
      if (overrideModel) body.override_model = overrideModel
      if (overridePolicy) body.override_policy_id = overridePolicy
      const res = await authorizedFetch(`${API_BASE}/api/v1/gateway/traces/${traceId}/replay`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      onReplayed()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed')
    } finally {
      setReplaying(false)
    }
  }

  return (
    <div
      role="dialog"
      aria-label="Trace detail"
      style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 560,
        background: 'var(--bg)', borderLeft: '1px solid var(--line)',
        boxShadow: '-4px 0 16px rgba(0,0,0,0.2)', zIndex: 50, overflowY: 'auto',
      }}
      data-testid="trace-drawer"
    >
      <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between', position: 'sticky', top: 0, background: 'var(--bg)', zIndex: 1 }}>
        <span>Trace · {traceId.slice(0, 8)}</span>
        <button className="btn btn-sm" onClick={onClose} aria-label="Close">×</button>
      </div>
      <div style={{ padding: 16 }}>
        {!detail && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
        {detail && (
          <>
            <Section label="Summary">
              <KV label="Route" value={detail.route} />
              <KV label="Model" value={detail.model_used ?? detail.model_requested} />
              <KV label="Provider" value={detail.provider ?? '—'} />
              <KV label="Status" value={detail.status} />
              <KV label="Latency" value={formatMs(detail.latency_ms)} />
              <KV label="TTFT" value={formatMs(detail.ttft_ms)} />
              <KV label="Cost" value={formatCents(detail.cost_cents)} />
              <KV label="Tokens in/out" value={`${detail.tokens_in ?? 0} / ${detail.tokens_out ?? 0}`} />
              <KV label="Cache" value={detail.cache_hit ? 'hit' : 'miss'} />
            </Section>

            <Section label="Routing decision">
              <pre style={{ fontSize: 10, padding: 8, background: 'var(--bg-2)', borderRadius: 4, overflow: 'auto', maxHeight: 160 }}>
                {JSON.stringify(detail.routing_decision, null, 2)}
              </pre>
            </Section>

            <Section label="Guardrail verdicts">
              {(detail.guardrail_verdicts ?? []).length === 0
                ? <p style={{ fontSize: 11, color: 'var(--ink-3)' }}>None.</p>
                : detail.guardrail_verdicts.map((v, i) => (
                  <div key={i} style={{ fontSize: 11, padding: 4 }}>
                    {v.guardrail}: <span className={`pill pill-${v.decision === 'block' ? 'red' : v.decision === 'allow' ? 'green' : 'yellow'}`}>{v.decision}</span>
                  </div>
                ))
              }
            </Section>

            <Section label="Request">
              <pre style={{ fontSize: 10, padding: 8, background: 'var(--bg-2)', borderRadius: 4, overflow: 'auto', maxHeight: 200 }}>
                {JSON.stringify(detail.request_json, null, 2)}
              </pre>
            </Section>

            <Section label="Response">
              <pre style={{ fontSize: 10, padding: 8, background: 'var(--bg-2)', borderRadius: 4, overflow: 'auto', maxHeight: 200 }}>
                {JSON.stringify(detail.response_json, null, 2)}
              </pre>
            </Section>

            <Section label="Replay">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontSize: 10, color: 'var(--ink-3)' }}>Override model</label>
                <Select
                  value={overrideModel}
                  onChange={(e) => setOverrideModel(e.target.value)}
                  data-testid="replay-model"
                size="sm"
                inline
                >
                  <option value="">(same as original)</option>
                  {models.map((m) => <option key={m.id} value={m.model_id}>{m.display_name || m.model_id}</option>)}
                </Select>
                <label style={{ fontSize: 10, color: 'var(--ink-3)' }}>Override routing policy</label>
                <Select
                  value={overridePolicy}
                  onChange={(e) => setOverridePolicy(e.target.value)}
                  data-testid="replay-policy"
                size="sm"
                inline
                >
                  <option value="">(same as original)</option>
                  {policies.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </Select>
                <button
                  className="btn btn-primary"
                  onClick={replay}
                  disabled={replaying}
                  data-testid="replay-button"
                >
                  {replaying ? 'Replaying…' : 'Replay'}
                </button>
                {err && <p style={{ fontSize: 11, color: 'var(--red)' }}>{err}</p>}
              </div>
            </Section>
          </>
        )}
      </div>
    </div>
  )
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--ink-3)', marginBottom: 6 }}>{label}</div>
      {children}
    </section>
  )
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', fontSize: 11, padding: '2px 0' }}>
      <span style={{ color: 'var(--ink-3)' }}>{label}</span>
      <span style={{ fontFamily: 'var(--font-mono)' }}>{value}</span>
    </div>
  )
}
