/**
 * Mirrors the RAG management HTTP surface (eval, playground, analytics).
 *
 * Kept thin on purpose — the page code consumes the API shapes directly and
 * only the *logic* (validation, summarisation, sort) lives in pure helpers
 * so it can be unit-tested without React.
 */

// ── eval ────────────────────────────────────────────────────────────────

export type EvalRecord = {
  id: string
  query: string
  expected_doc_ids: string[]
  relevance_grades?: Record<string, number>
  expected_answer?: string
  judges: string[]
}

export type EvalTestSet = {
  id: string
  kb_id: number
  name: string
  records: EvalRecord[]
  judge_model: string | null
  judge_temperature: number
  created_at: string
  updated_at: string
}

export type EvalRunRowResult = {
  record_id: string
  retrieved_doc_ids: string[]
  metrics: Record<string, number>
  answer: string
  judge_scores: Record<string, number>
  error: string | null
}

export type EvalRunSummary = {
  pass_rate: number
  mean_metrics: Record<string, number>
  n: number
  regression: boolean
  regression_delta: number
}

export type EvalRunOut = {
  id: string
  eval_id: string
  snapshot_id: string | null
  summary: EvalRunSummary
  results: EvalRunRowResult[]
  regression: boolean
  ran_at: string
}

// ── playground ──────────────────────────────────────────────────────────

export type PlaygroundSettings = {
  top_k: number
  min_score: number
  rerank: boolean
  model?: string | null
  tone?: string | null
  language?: string | null
}

export type RetrievedChunk = {
  chunk_id: string
  document_id: string
  text: string
  score: number
  meta: Record<string, unknown>
}

export type PlaygroundResponse = {
  session_id: string | null
  query: string
  retrieved: RetrievedChunk[]
  answer: string
  citations: Array<Record<string, unknown>>
}

export type PlaygroundSession = {
  id: string
  kb_id: number
  prompt: string
  settings: PlaygroundSettings
  retrieved: RetrievedChunk[]
  answer: string | null
  created_at: string
}

// ── analytics ───────────────────────────────────────────────────────────

export type QueryStat = {
  query: string
  count: number
  avg_hits: number
  avg_latency_ms: number
}

export type CitationHitRate = {
  document_id: string
  citations: number
  queries: number
  rate: number
}

export type FeedbackBreakdown = {
  up: number
  down: number
  ratio: number
}

export type CostPoint = {
  bucket: string
  cost_cents: number
  queries: number
}

export type CostSeries = {
  granularity: string
  points: CostPoint[]
  total_cents: number
}

export type AnalyticsOverview = {
  top_queries: QueryStat[]
  zero_result_queries: QueryStat[]
  citation_hit_rate: CitationHitRate[]
  feedback: FeedbackBreakdown
  cost: CostSeries
  total_queries: number
  total_cost_cents: number
}

// ── connector marketplace presets ───────────────────────────────────────

export type ConnectorPreset = {
  kind: string
  label: string
  blurb: string
  config_schema?: Record<string, unknown>
  // categories purely for UI grouping
  category: 'storage' | 'docs' | 'chat' | 'support' | 'code' | 'crm' | 'web' | 'mail'
}

export type SearchProviderKind = 'tavily' | 'exa' | 'brave' | 'bing' | 'google_cse' | 'internal'

export type SearchProviderConfig = {
  id: string
  kind: SearchProviderKind
  enabled: boolean
  default_for_web: boolean
  config: Record<string, unknown>
}
