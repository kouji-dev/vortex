import { Select } from '~/components/ui/select'
import { createFileRoute } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import * as React from 'react'
import { fetchGatewayModels } from '~/lib/gateway-api'
import {
  capabilityTags,
  filterModels,
  formatPricePerK,
  sortModels,
  type ModelFilter,
} from '~/lib/gateway-models'
import type { ModelInfo } from '~/lib/gateway-types'

export const Route = createFileRoute('/gateway/models')({
  component: ModelsPage,
})

const CAP_FILTERS: { value: ModelFilter['capability'] | ''; label: string }[] = [
  { value: '', label: 'Any capability' },
  { value: 'streaming', label: 'Streaming' },
  { value: 'tools', label: 'Tools' },
  { value: 'vision', label: 'Vision' },
  { value: 'thinking', label: 'Thinking' },
  { value: 'cache', label: 'Cache' },
  { value: 'json_mode', label: 'JSON mode' },
]

function ModelsPage() {
  const list = useQuery({ queryKey: ['gateway', 'models'], queryFn: fetchGatewayModels })
  const [search, setSearch] = React.useState('')
  const [provider, setProvider] = React.useState('')
  const [capability, setCapability] = React.useState<ModelFilter['capability'] | ''>('')
  const [includeDeprecated, setIncludeDeprecated] = React.useState(false)

  const providerOptions = React.useMemo(() => {
    const set = new Set<string>()
    for (const m of list.data ?? []) set.add(m.provider)
    return Array.from(set).sort()
  }, [list.data])

  const visible = React.useMemo(() => {
    if (!list.data) return [] as ModelInfo[]
    return sortModels(
      filterModels(list.data, {
        provider: provider || undefined,
        capability: (capability as ModelFilter['capability']) || undefined,
        search,
        includeDeprecated,
      }),
    )
  }, [list.data, provider, capability, search, includeDeprecated])

  return (
    <div className="panel" data-testid="gw-models">
      <div className="panel-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <span>Model catalog</span>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            className="gw-input"
            placeholder="Search…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            data-testid="gw-models-search"
          />
          <Select
            className="gw-input"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            data-testid="gw-models-provider"
          size="sm"
          inline
          >
            <option value="">All providers</option>
            {providerOptions.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </Select>
          <Select
            className="gw-input"
            value={capability ?? ''}
            onChange={(e) => setCapability((e.target.value || '') as ModelFilter['capability'] | '')}
            data-testid="gw-models-capability"
          size="sm"
          inline
          >
            {CAP_FILTERS.map((c) => (
              <option key={c.value || 'any'} value={c.value ?? ''}>{c.label}</option>
            ))}
          </Select>
          <label style={{ fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}>
            <input
              type="checkbox"
              checked={includeDeprecated}
              onChange={(e) => setIncludeDeprecated(e.target.checked)}
              data-testid="gw-models-deprecated"
            />
            deprecated
          </label>
        </div>
      </div>
      <div className="panel-body" style={{ padding: 16 }}>
        {list.isPending && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>}
        {list.error && (
          <p style={{ fontSize: 12, color: 'var(--red)' }}>{(list.error as Error).message}</p>
        )}
        {list.data && <ModelsTable rows={visible} />}
      </div>
    </div>
  )
}

function ModelsTable({ rows }: { rows: ModelInfo[] }) {
  if (rows.length === 0) {
    return <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>No models match.</p>
  }
  return (
    <div className="tbl" data-testid="gw-models-table">
      <div className="audit-row" style={headerRow}>
        <span>Model</span>
        <span>Provider</span>
        <span>Capabilities</span>
        <span>Input</span>
        <span>Output</span>
        <span>Cache read</span>
      </div>
      {rows.map((m) => {
        const tags = capabilityTags(m.capabilities)
        return (
          <div key={m.id} className="audit-row" style={dataRow}>
            <span style={{ color: 'var(--ink)' }}>
              {m.display_name}
              <div className="meta" style={{ fontFamily: 'var(--font-mono)' }}>{m.model_id}</div>
            </span>
            <span className="meta">{m.provider}</span>
            <span style={{ overflow: 'hidden' }}>
              {tags.length === 0 ? (
                <span className="meta">—</span>
              ) : (
                tags.map((t) => <span key={t} className="gw-cap">{t}</span>)
              )}
            </span>
            <span className="meta">{formatPricePerK(m.price_input_per_1k_cents)}</span>
            <span className="meta">{formatPricePerK(m.price_output_per_1k_cents)}</span>
            <span className="meta">
              {m.price_cache_read_per_1k_cents == null ? '—' : formatPricePerK(m.price_cache_read_per_1k_cents)}
            </span>
          </div>
        )
      })}
    </div>
  )
}

const headerRow: React.CSSProperties = {
  gridTemplateColumns: '1.4fr 110px 1.4fr 110px 110px 110px',
  background: 'var(--bg-2)',
  borderBottom: '1px solid var(--line)',
  fontWeight: 600,
  fontSize: 10,
  color: 'var(--ink-3)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
}
const dataRow: React.CSSProperties = {
  gridTemplateColumns: '1.4fr 110px 1.4fr 110px 110px 110px',
}
