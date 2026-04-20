import * as React from 'react'
import { authorizedFetch } from '~/lib/authorizedFetch'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

// ── helpers ─────────────────────────────────────────────────────────────────

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function daysAgo(n: number): Date {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d
}

function relativeTime(iso: string): string {
  const d = (Date.now() - new Date(iso).getTime()) / 60000
  if (d < 60) return `${Math.max(1, Math.round(d))}m ago`
  if (d < 60 * 24) return `${Math.round(d / 60)}h ago`
  return `${Math.round(d / (60 * 24))}d ago`
}

// ── API types ────────────────────────────────────────────────────────────────

interface KpiCard {
  label: string
  value: number | string
  unit: string
  delta_pct: number | null
  is_estimate: boolean
}

interface SummaryRow {
  key: string
  label: string
  messages: number
  input_tokens: number
  output_tokens: number
  cost_usd: string
  estimated_ratio: number
}

interface SummaryResponse {
  kpis: KpiCard[]
  by_model: SummaryRow[]
  by_user: SummaryRow[]
  by_provider: SummaryRow[]
  by_capability: SummaryRow[]
  by_tool: SummaryRow[]
}

interface TrendPoint {
  ts: string
  value: number
  label: string
}

interface TrendResponse {
  points: TrendPoint[]
  grain: string
  by: string
}

interface ThreadRow {
  id: number
  title: string | null
  user_id: number
  model: string | null
  created_at: string
  last_message_at: string | null
  total_cost_usd: string
  item_count: number
}

interface ThreadsResponse {
  rows: ThreadRow[]
  total: number
  page: number
  page_size: number
}

interface TimelineItem {
  id: number
  turn_id: string
  kind: string
  role: string | null
  status: string
  provider: string | null
  model: string | null
  cost_usd: string | null
  cost_estimated: boolean
  latency_ms: number | null
  data: Record<string, unknown>
  created_at: string
}

interface TimelineResponse {
  thread_id: number
  items: TimelineItem[]
}

// ── sub-components ───────────────────────────────────────────────────────────

function KpiStrip({ kpis, loading }: { kpis: KpiCard[]; loading: boolean }) {
  if (loading && kpis.length === 0) {
    return (
      <div className="kpi-row">
        <div className="kpi">
          <div className="kpi-label">Loading…</div>
        </div>
      </div>
    )
  }
  return (
    <div className="kpi-row">
      {kpis.map((k) => (
        <div key={k.label} className="kpi">
          <div className="kpi-label">
            {k.label}
            {k.is_estimate && ' *'}
          </div>
          <div className="kpi-value">
            {typeof k.value === 'number' ? k.value.toLocaleString() : k.value}
            {k.unit && (
              <span className="text-[11px] ml-0.5 text-ink-3">
                {k.unit}
              </span>
            )}
          </div>
          {k.delta_pct != null && (
            <div
              className={`kpi-delta ${k.delta_pct > 0 ? 'up' : k.delta_pct < 0 ? 'down' : 'flat'}`}
            >
              {k.delta_pct > 0 ? '▲' : k.delta_pct < 0 ? '▼' : '—'}{' '}
              {Math.abs(k.delta_pct).toFixed(1)}%
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function TrendChart({ points }: { points: TrendPoint[] }) {
  const max = Math.max(...points.map((p) => p.value), 0.0001)
  const W = 600
  const H = 60
  const BAR_W = Math.max(2, Math.floor(W / points.length - 1))
  return (
    <div style={{ overflowX: 'auto' }}>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block', height: H }}>
        {points.map((p, i) => {
          const barH = Math.max(2, (p.value / max) * (H - 4))
          return (
            <rect
              key={p.ts}
              x={i * (W / points.length)}
              y={H - barH}
              width={BAR_W}
              height={barH}
              fill="var(--brand)"
              opacity={0.7}
            >
              <title>
                {new Date(p.ts).toLocaleDateString()} — ${Number(p.value).toFixed(4)}
              </title>
            </rect>
          )
        })}
      </svg>
    </div>
  )
}

type SortKey = 'messages' | 'input_tokens' | 'output_tokens' | 'cost_usd' | 'estimated_ratio'

function SummaryTable({ rows, loading }: { rows: SummaryRow[]; loading: boolean }) {
  const [sortKey, setSortKey] = React.useState<SortKey>('cost_usd')
  const [sortDir, setSortDir] = React.useState<'asc' | 'desc'>('desc')

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  function getVal(row: SummaryRow, key: SortKey): number {
    return key === 'cost_usd' ? parseFloat(row.cost_usd) : row[key]
  }
  const sorted = [...rows].sort((a, b) => {
    const av = getVal(a, sortKey)
    const bv = getVal(b, sortKey)
    return sortDir === 'desc' ? bv - av : av - bv
  })

  if (loading && rows.length === 0) {
    return <p className="px-3.5 py-3 text-[12px] text-ink-3">Loading…</p>
  }
  if (rows.length === 0) {
    return <p className="px-3.5 py-3 text-[12px] text-ink-3">No data for this period.</p>
  }

  const arrow = (key: SortKey) =>
    sortKey === key ? (sortDir === 'desc' ? ' ▼' : ' ▲') : ''

  return (
    <table className="tbl">
      <thead>
        <tr>
          <th>Name</th>
          <th
            className="num cursor-pointer"
            onClick={() => toggleSort('messages')}
          >
            Messages{arrow('messages')}
          </th>
          <th
            className="num cursor-pointer"
            onClick={() => toggleSort('input_tokens')}
          >
            Input tok{arrow('input_tokens')}
          </th>
          <th
            className="num cursor-pointer"
            onClick={() => toggleSort('output_tokens')}
          >
            Output tok{arrow('output_tokens')}
          </th>
          <th
            className="num cursor-pointer"
            onClick={() => toggleSort('cost_usd')}
          >
            Cost (USD){arrow('cost_usd')}
          </th>
          <th
            className="num cursor-pointer"
            onClick={() => toggleSort('estimated_ratio')}
          >
            Est %{arrow('estimated_ratio')}
          </th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((r) => (
          <tr key={r.key}>
            <td className="name-cell">{r.label || r.key}</td>
            <td className="num">{r.messages.toLocaleString()}</td>
            <td className="num">{r.input_tokens.toLocaleString()}</td>
            <td className="num">{r.output_tokens.toLocaleString()}</td>
            <td className="num">${parseFloat(r.cost_usd).toFixed(4)}</td>
            <td className="num muted">{(r.estimated_ratio * 100).toFixed(0)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function TokenVolumeChart({ rows }: { rows: SummaryRow[] }) {
  if (rows.length === 0) return null
  const max = Math.max(...rows.map((r) => r.input_tokens + r.output_tokens), 1)
  const W = 600
  const H = 60
  const BAR_W = Math.max(4, Math.floor(W / rows.length) - 2)
  return (
    <div style={{ overflowX: 'auto' }}>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block', height: H }}>
        {rows.map((r, i) => {
          const total = r.input_tokens + r.output_tokens
          const barH = Math.max(2, (total / max) * (H - 4))
          return (
            <rect
              key={r.key}
              x={i * (W / rows.length)}
              y={H - barH}
              width={BAR_W}
              height={barH}
              fill="var(--brand)"
              opacity={0.5}
            >
              <title>
                {r.label || r.key} — {total.toLocaleString()} tokens
              </title>
            </rect>
          )
        })}
      </svg>
    </div>
  )
}

function ThreadsTable({
  data,
  loading,
  page,
  onPageChange,
  onSelectThread,
}: {
  data: ThreadsResponse | null
  loading: boolean
  page: number
  onPageChange: (p: number) => void
  onSelectThread: (id: number) => void
}) {
  if (loading && !data) {
    return <p className="px-3.5 py-3 text-[12px] text-ink-3">Loading…</p>
  }
  if (!data || data.rows.length === 0) {
    return <p className="px-3.5 py-3 text-[12px] text-ink-3">No threads in this period.</p>
  }
  const totalPages = Math.ceil(data.total / data.page_size)
  return (
    <>
      <table className="tbl">
        <thead>
          <tr>
            <th>Thread</th>
            <th>Model</th>
            <th className="num">Items</th>
            <th className="num">Cost (USD)</th>
            <th>Last active</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => (
            <tr key={r.id} className="cursor-pointer" onClick={() => onSelectThread(r.id)}>
              <td className="name-cell">
                {r.title ?? `Thread #${r.id}`}
                <div className="sub">#{r.id}</div>
              </td>
              <td>
                <span className="mono text-[10px] text-ink-3">
                  {r.model ?? '—'}
                </span>
              </td>
              <td className="num">{r.item_count}</td>
              <td className="num">${parseFloat(r.total_cost_usd).toFixed(4)}</td>
              <td className="text-[11px] text-ink-3">
                {r.last_message_at ? relativeTime(r.last_message_at) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {totalPages > 1 && (
        <div className="flex gap-1.5 px-3.5 py-2 justify-end">
          <button
            className="btn btn-xs"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            ← Prev
          </button>
          <span className="text-[11px] text-ink-3 self-center">
            {page} / {totalPages}
          </span>
          <button
            className="btn btn-xs"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
          >
            Next →
          </button>
        </div>
      )}
    </>
  )
}

const KIND_ICONS: Record<string, string> = {
  user_message: '👤',
  llm_call: '🧠',
  assistant_text: '💬',
  tool_call: '🔧',
  server_tool_use: '🔍',
  thinking: '💭',
  citation: '📎',
  memory_pill: '🧪',
  turn_end: '✅',
  error: '❌',
}

function TimelineView({ items }: { items: TimelineItem[] }) {
  return (
    <div className="px-3.5 py-2">
      {items.map((item) => (
        <div key={item.id} className="flex gap-2.5 py-1.5 border-b border-line">
          <div className="text-base w-5.5 shrink-0 text-center">
            {KIND_ICONS[item.kind] ?? '•'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex gap-2 items-baseline flex-wrap">
              <span className="mono text-[11px] text-ink font-semibold">{item.kind}</span>
              {item.model && (
                <span className="mono text-[10px] text-ink-3">{item.model}</span>
              )}
              {item.provider && (
                <span className="text-[10px] text-ink-3">{item.provider}</span>
              )}
              {item.cost_usd && parseFloat(item.cost_usd) > 0 && (
                <span className="mono text-[10px] text-ok">
                  ${parseFloat(item.cost_usd).toFixed(6)}{item.cost_estimated && '*'}
                </span>
              )}
              {item.latency_ms != null && (
                <span className="text-[10px] text-ink-3">{item.latency_ms}ms</span>
              )}
            </div>
            {item.kind === 'assistant_text' && item.data.text != null && (
              <div className="text-[11px] text-ink-2 mt-0.5 overflow-hidden max-h-10 text-ellipsis">
                {String(item.data.text).slice(0, 200)}
              </div>
            )}
            {item.kind === 'tool_call' && item.data.tool_name != null && (
              <div className="mono text-[10px] text-ink-3 mt-0.5">
                {String(item.data.tool_name)}
              </div>
            )}
            {item.kind === 'llm_call' && (
              <div className="mono text-[10px] text-ink-3 mt-0.5">
                {item.data.input_tokens != null &&
                  `${item.data.input_tokens}↑ ${item.data.output_tokens}↓ tokens`}
              </div>
            )}
          </div>
          <div className="text-[10px] text-ink-3 whitespace-nowrap self-start">
            {new Date(item.created_at).toLocaleTimeString()}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── main page ────────────────────────────────────────────────────────────────

export function ConsumptionPage() {
  const [start, setStart] = React.useState(() => isoDate(daysAgo(90)))
  const [end, setEnd] = React.useState(() => isoDate(new Date()))

  const [groupTab, setGroupTab] = React.useState<
    'model' | 'user' | 'provider' | 'capability' | 'tool'
  >('model')

  const [selectedThread, setSelectedThread] = React.useState<number | null>(null)
  const [timeline, setTimeline] = React.useState<TimelineItem[] | null>(null)
  const [timelineLoading, setTimelineLoading] = React.useState(false)

  const [page, setPage] = React.useState(1)

  const [summary, setSummary] = React.useState<SummaryResponse | null>(null)
  const [summaryLoading, setSummaryLoading] = React.useState(false)

  const [threadsData, setThreadsData] = React.useState<ThreadsResponse | null>(null)
  const [threadsLoading, setThreadsLoading] = React.useState(false)

  const [trend, setTrend] = React.useState<TrendResponse | null>(null)

  async function fetchSummary() {
    setSummaryLoading(true)
    try {
      const r = await authorizedFetch(
        `${API_BASE}/api/admin/consumption/summary?start=${start}&end=${end}`,
      )
      if (r.ok) setSummary(await r.json())
    } catch (err) {
      console.error('fetchSummary failed', err)
    } finally {
      setSummaryLoading(false)
    }
  }

  async function fetchTrend() {
    try {
      const r = await authorizedFetch(
        `${API_BASE}/api/admin/consumption/trend?start=${start}&end=${end}&grain=day&by=kind`,
      )
      if (r.ok) setTrend(await r.json())
    } catch (err) {
      console.error('fetchTrend failed', err)
    }
  }

  async function fetchThreads() {
    setThreadsLoading(true)
    try {
      const r = await authorizedFetch(
        `${API_BASE}/api/admin/consumption/threads?start=${start}&end=${end}&page=${page}&page_size=20`,
      )
      if (r.ok) setThreadsData(await r.json())
    } catch (err) {
      console.error('fetchThreads failed', err)
    } finally {
      setThreadsLoading(false)
    }
  }

  async function openTimeline(threadId: number) {
    setSelectedThread(threadId)
    setTimeline(null)
    setTimelineLoading(true)
    try {
      const r = await authorizedFetch(
        `${API_BASE}/api/admin/consumption/threads/${threadId}/timeline`,
      )
      if (r.ok) setTimeline((await r.json() as TimelineResponse).items)
    } catch (err) {
      console.error('openTimeline failed', err)
    } finally {
      setTimelineLoading(false)
    }
  }

  React.useEffect(() => {
    fetchSummary()
    fetchTrend()
    fetchThreads()
    const id = setInterval(() => {
      fetchSummary()
      fetchTrend()
      fetchThreads()
    }, 30_000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [start, end, page])

  const groupRows = summary
    ? (summary[`by_${groupTab}` as keyof SummaryResponse] as SummaryRow[])
    : []

  return (
    <div className="main-inner" data-testid="consumption-page">
      <div className="screen-head">
        <div>
          <h1>Consumption</h1>
          <div className="sub">Cost · tokens · models · threads</div>
        </div>
        <div className="flex gap-2 items-center">
          <label className="text-[11px] text-ink-3 flex items-center gap-1.5">
            From
            <input
              type="date"
              value={start}
              onChange={(e) => {
                setStart(e.target.value)
                setPage(1)
              }}
              className="input !w-auto !py-0.5 !px-2 !text-[11px]"
            />
          </label>
          <label className="text-[11px] text-ink-3 flex items-center gap-1.5">
            To
            <input
              type="date"
              value={end}
              onChange={(e) => {
                setEnd(e.target.value)
                setPage(1)
              }}
              className="input !w-auto !py-0.5 !px-2 !text-[11px]"
            />
          </label>
        </div>
      </div>

      {/* KPI Strip */}
      <KpiStrip kpis={summary?.kpis ?? []} loading={summaryLoading} />

      {/* Trend sparkline */}
      {trend && trend.points.length > 0 && (
        <div className="panel mb-4">
          <div className="panel-head">Spend trend (daily)</div>
          <div className="panel-body">
            <TrendChart points={trend.points} />
          </div>
        </div>
      )}

      {/* Token volume by model */}
      {summary && summary.by_model.length > 0 && (
        <div className="panel mb-4">
          <div className="panel-head">Token volume by model</div>
          <div className="panel-body">
            <TokenVolumeChart rows={summary.by_model} />
          </div>
        </div>
      )}

      {/* Grouped tables */}
      <div className="panel mb-4">
        <div className="panel-head flex items-center gap-2">
          <span>Breakdown</span>
          <div className="tabs ml-auto mb-0">
            {(['model', 'user', 'provider', 'capability', 'tool'] as const).map((t) => (
              <button
                key={t}
                className={`tab${groupTab === t ? ' active' : ''}`}
                onClick={() => setGroupTab(t)}
              >
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>
        </div>
        <SummaryTable rows={groupRows} loading={summaryLoading} />
      </div>

      {/* Thread list */}
      <div className="panel">
        <div className="panel-head">Threads</div>
        <ThreadsTable
          data={threadsData}
          loading={threadsLoading}
          page={page}
          onPageChange={setPage}
          onSelectThread={openTimeline}
        />
      </div>

      {/* Timeline drilldown */}
      {selectedThread != null && (
        <div className="panel mt-4">
          <div className="panel-head flex items-center gap-2">
            <span>Timeline — Thread #{selectedThread}</span>
            <button
              className="btn btn-xs ml-auto"
              onClick={() => setSelectedThread(null)}
            >
              Close
            </button>
          </div>
          {timelineLoading && (
            <p className="px-3.5 py-3 text-[12px] text-ink-3">Loading…</p>
          )}
          {timeline && <TimelineView items={timeline} />}
        </div>
      )}
    </div>
  )
}
