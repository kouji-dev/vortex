/**
 * Q11 — Connector marketplace.
 *
 * Static catalogue of connector presets grouped by category, with search.
 * Selecting a preset would normally launch a "configure on a KB" wizard;
 * for v1 it deep-links to the KB list so the user picks a KB to install
 * the connector against.
 */
import { Link, createFileRoute } from '@tanstack/react-router'
import * as React from 'react'

import { filterPresets, presetsByCategory } from '~/lib/rag-logic'

export const Route = createFileRoute('/rag/marketplace')({
  component: MarketplacePage,
})

function MarketplacePage() {
  const [q, setQ] = React.useState('')
  const filtered = filterPresets(q)
  const byCat = React.useMemo(() => {
    const all = presetsByCategory()
    if (!q.trim()) return all
    const keep = new Set(filtered.map((p) => p.kind))
    const out: typeof all = {}
    for (const [cat, list] of Object.entries(all)) {
      const subset = list.filter((p) => keep.has(p.kind))
      if (subset.length) out[cat] = subset
    }
    return out
  }, [filtered, q])

  return (
    <div className="panel" data-testid="rag-marketplace">
      <div className="panel-head">
        <span>Connector marketplace</span>
        <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>{filtered.length} connectors</span>
      </div>
      <div className="panel-body" style={{ padding: 12 }}>
        <input
          className="rag-input"
          placeholder="Search connectors"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          data-testid="rag-marketplace-search"
        />
        {Object.entries(byCat).map(([cat, presets]) => (
          <div key={cat}>
            <div className="rag-cat">{cat}</div>
            <div className="rag-tile-grid">
              {presets.map((p) => (
                <Link
                  key={p.kind}
                  to="/rag/kbs"
                  className="rag-tile"
                  data-testid={`rag-marketplace-${p.kind}`}
                >
                  <h4>{p.label}</h4>
                  <p>{p.blurb}</p>
                </Link>
              ))}
            </div>
          </div>
        ))}
        {!filtered.length && (
          <p style={{ fontSize: 12, color: 'var(--ink-3)', textAlign: 'center', padding: 16 }}>
            No connectors match.
          </p>
        )}
      </div>
    </div>
  )
}
