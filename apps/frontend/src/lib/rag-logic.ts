/**
 * Pure logic for the RAG pages.
 *
 * Page components stay focused on layout + data fetching; everything that's
 * worth a unit test (validation, formatting, sort, summarise) lives here so
 * it can be exercised in a vanilla node:test runner with no DOM.
 */

import type {
  AnalyticsOverview,
  ConnectorPreset,
  EvalRecord,
  EvalRunOut,
  QueryStat,
} from './rag-types'

// ── formatting helpers ──────────────────────────────────────────────────

export function formatPct(x: number): string {
  if (!Number.isFinite(x)) return '—'
  return `${(x * 100).toFixed(1)}%`
}

export function formatCents(cents: number): string {
  if (!Number.isFinite(cents)) return '—'
  if (cents < 100) return `${cents.toFixed(2)}¢`
  return `$${(cents / 100).toFixed(2)}`
}

export function formatLatencyMs(ms: number): string {
  if (!Number.isFinite(ms)) return '—'
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

export function formatDelta(delta: number): string {
  if (!Number.isFinite(delta) || delta === 0) return '0%'
  const sign = delta > 0 ? '+' : ''
  return `${sign}${(delta * 100).toFixed(1)}%`
}

// ── eval ────────────────────────────────────────────────────────────────

export function validateEvalName(name: string): string | null {
  const trimmed = name.trim()
  if (!trimmed) return 'Name required'
  if (trimmed.length > 255) return 'Name too long (max 255)'
  return null
}

export function validateEvalRecord(rec: EvalRecord): string | null {
  if (!rec.id.trim()) return 'Record id required'
  if (!rec.query.trim()) return 'Query required'
  if (rec.judges.length === 0) return 'At least one judge required'
  return null
}

export function parseJudgeSpec(spec: string): { name: string; k: number | null } {
  const at = spec.indexOf('@')
  if (at < 0) return { name: spec.trim(), k: null }
  const name = spec.slice(0, at).trim()
  const k = Number(spec.slice(at + 1).trim())
  return { name, k: Number.isFinite(k) ? k : null }
}

export function summariseRun(run: EvalRunOut): {
  passRate: string
  primaryMetric: string | null
  regression: 'up' | 'down' | 'flat'
  delta: string
  n: number
} {
  const entries = Object.entries(run.summary.mean_metrics)
  const primary = entries[0]?.[0] ?? null
  let regression: 'up' | 'down' | 'flat' = 'flat'
  if (run.summary.regression_delta > 0.005) regression = 'up'
  else if (run.summary.regression_delta < -0.005) regression = 'down'
  return {
    passRate: formatPct(run.summary.pass_rate),
    primaryMetric: primary,
    regression,
    delta: formatDelta(run.summary.regression_delta),
    n: run.summary.n,
  }
}

/** Compare two runs and return the per-metric delta (newer minus older). */
export function compareRuns(
  newer: EvalRunOut,
  older: EvalRunOut,
): Array<{ metric: string; newer: number; older: number; delta: number }> {
  const keys = new Set<string>([
    ...Object.keys(newer.summary.mean_metrics),
    ...Object.keys(older.summary.mean_metrics),
  ])
  const out: Array<{ metric: string; newer: number; older: number; delta: number }> = []
  for (const m of keys) {
    const n = newer.summary.mean_metrics[m] ?? 0
    const o = older.summary.mean_metrics[m] ?? 0
    out.push({ metric: m, newer: n, older: o, delta: n - o })
  }
  out.sort((a, b) => a.metric.localeCompare(b.metric))
  return out
}

// ── analytics ───────────────────────────────────────────────────────────

export function sortQueriesByCount(stats: QueryStat[]): QueryStat[] {
  return [...stats].sort((a, b) => b.count - a.count || a.query.localeCompare(b.query))
}

export function computeFeedbackRatio(up: number, down: number): number {
  const total = up + down
  if (total <= 0) return 0
  return up / total
}

export function summariseAnalytics(o: AnalyticsOverview): {
  totalQueries: number
  totalCost: string
  hitRate: string
  zeroRate: string
  thumbsUp: string
} {
  const zero = o.zero_result_queries.reduce((s, q) => s + q.count, 0)
  const zeroRate = o.total_queries > 0 ? zero / o.total_queries : 0
  const cited = o.citation_hit_rate.reduce((s, c) => s + c.citations, 0)
  const hitRate = o.total_queries > 0 ? cited / o.total_queries : 0
  return {
    totalQueries: o.total_queries,
    totalCost: formatCents(o.total_cost_cents),
    hitRate: formatPct(hitRate),
    zeroRate: formatPct(zeroRate),
    thumbsUp: formatPct(o.feedback.ratio),
  }
}

// ── connector marketplace ──────────────────────────────────────────────

export const CONNECTOR_PRESETS: ConnectorPreset[] = [
  {
    kind: 'web_crawler',
    label: 'Web crawler',
    blurb: 'Sitemap + robots-aware HTTP crawl with rate limiting.',
    category: 'web',
  },
  {
    kind: 'file_upload',
    label: 'File upload',
    blurb: 'Manual uploads to a BlobStore-backed bucket.',
    category: 'storage',
  },
  {
    kind: 's3',
    label: 'Amazon S3',
    blurb: 'Sync objects under a prefix; ETag delta cursor.',
    category: 'storage',
  },
  {
    kind: 'azure_blob',
    label: 'Azure Blob',
    blurb: 'Service-principal auth; container/prefix scoping.',
    category: 'storage',
  },
  {
    kind: 'gcs',
    label: 'Google Cloud Storage',
    blurb: 'Service-account JSON; generation-based delta.',
    category: 'storage',
  },
  {
    kind: 'gdrive',
    label: 'Google Drive',
    blurb: 'OAuth; folder + shared-drive scope; ACL extraction.',
    category: 'docs',
  },
  {
    kind: 'sharepoint',
    label: 'OneDrive / SharePoint',
    blurb: 'MS Graph; site + library scope; AAD ACL mapping.',
    category: 'docs',
  },
  {
    kind: 'confluence',
    label: 'Confluence',
    blurb: 'Cloud + server; space restrictions as ACL.',
    category: 'docs',
  },
  {
    kind: 'notion',
    label: 'Notion',
    blurb: 'Workspace token; databases + pages.',
    category: 'docs',
  },
  {
    kind: 'slack',
    label: 'Slack',
    blurb: 'Channels + threads + files; member-based ACL.',
    category: 'chat',
  },
  {
    kind: 'github',
    label: 'GitHub',
    blurb: 'README + docs/ + issues + PRs + wiki.',
    category: 'code',
  },
  {
    kind: 'gitlab',
    label: 'GitLab',
    blurb: 'Group/project scope; issues + repo docs.',
    category: 'code',
  },
  {
    kind: 'imap',
    label: 'IMAP shared mailbox',
    blurb: 'Label filter + attachment extraction.',
    category: 'mail',
  },
  {
    kind: 'salesforce',
    label: 'Salesforce Knowledge',
    blurb: 'KnowledgeArticleVersion with categories.',
    category: 'crm',
  },
  {
    kind: 'zendesk',
    label: 'Zendesk',
    blurb: 'Help center articles; tickets opt-in.',
    category: 'support',
  },
  {
    kind: 'intercom',
    label: 'Intercom',
    blurb: 'Articles + (opt-in) conversations.',
    category: 'support',
  },
  {
    kind: 'jira',
    label: 'Jira',
    blurb: 'Issue body + comments + attachments.',
    category: 'support',
  },
  {
    kind: 'http_generic',
    label: 'Generic HTTP API',
    blurb: 'JSONPath-configured cursor-paginated ingest.',
    category: 'web',
  },
]

export function presetsByCategory(): Record<string, ConnectorPreset[]> {
  const out: Record<string, ConnectorPreset[]> = {}
  for (const p of CONNECTOR_PRESETS) {
    ;(out[p.category] ??= []).push(p)
  }
  for (const k of Object.keys(out)) {
    out[k].sort((a, b) => a.label.localeCompare(b.label))
  }
  return out
}

export function filterPresets(query: string): ConnectorPreset[] {
  const q = query.trim().toLowerCase()
  if (!q) return CONNECTOR_PRESETS
  return CONNECTOR_PRESETS.filter(
    (p) =>
      p.label.toLowerCase().includes(q) ||
      p.kind.toLowerCase().includes(q) ||
      p.blurb.toLowerCase().includes(q),
  )
}

// ── search providers ────────────────────────────────────────────────────

export const SEARCH_PROVIDER_KINDS = [
  'tavily',
  'exa',
  'brave',
  'bing',
  'google_cse',
  'internal',
] as const

export function validateSearchProviderConfig(
  kind: string,
  config: Record<string, unknown>,
): string | null {
  if (kind === 'internal') return null
  const apiKey = (config?.api_key ?? '') as unknown
  if (typeof apiKey !== 'string' || apiKey.trim().length === 0) {
    return 'api_key required'
  }
  if (kind === 'google_cse') {
    const cx = config?.cx as unknown
    if (typeof cx !== 'string' || cx.trim().length === 0) {
      return 'cx (custom-search engine id) required'
    }
  }
  return null
}
