// apps/frontend/src/lib/gateway-types.ts
// Gateway UI shared types — mirrors server/api/src/ai_portal/gateway/*.
// Kept loose (string for ids, ISO strings for timestamps) to match the
// REST surface; tightened only where pure-logic UI code depends on shape.

// ---------- Providers ----------
export type ProviderKind =
  | 'anthropic'
  | 'openai'
  | 'azure_openai'
  | 'bedrock'
  | 'vertex'
  | 'gemini'
  | 'mistral'
  | 'ollama'
  | 'vllm'
  | 'together'
  | 'groq'
  | 'fireworks'

export interface ProviderCredential {
  id: string
  provider: ProviderKind
  label: string
  healthy: boolean
  last_health_at: string | null
}

// ---------- Models ----------
export interface ModelCapabilities {
  vision?: boolean
  tools?: boolean
  thinking?: boolean
  cache?: boolean
  json_mode?: boolean
  streaming?: boolean
}

export interface ModelInfo {
  id: string
  provider: ProviderKind
  model_id: string
  display_name: string
  capabilities: ModelCapabilities
  price_input_per_1k_cents: number
  price_output_per_1k_cents: number
  price_cache_read_per_1k_cents: number | null
  deprecated_at: string | null
}

// ---------- Routing ----------
export type RoutingStrategy =
  | 'static'
  | 'priority'
  | 'weighted'
  | 'cost_optimized'
  | 'latency_optimized'
  | 'capability_match'
  | 'custom_rules'

export interface RoutingPolicy {
  id: string
  name: string
  strategy: RoutingStrategy
  rules_json: unknown
  created_at: string
}

export interface ModelAlias {
  id: string
  alias: string
  routing_policy_id: string
}

// ---------- Rate limits ----------
export type RateLimitDimension = 'rpm' | 'tpm' | 'concurrent'

export interface RateLimitRule {
  id: string
  scope_json: Record<string, unknown>
  dimension: RateLimitDimension
  period: string // e.g. '1m'
  limit: number
  burst: number | null
}

// ---------- Guardrails ----------
export type GuardrailKind =
  | 'regex'
  | 'presidio'
  | 'openai_moderation'
  | 'llamaguard'
  | 'prompt_injection_classifier'
  | 'secret_scanner'
  | 'topic_filter'
  | 'schema_validator'
  | 'custom_classifier'

export type GuardrailAction = 'allow' | 'redact' | 'block' | 'flag'

export interface GuardrailStep {
  kind: GuardrailKind
  config: Record<string, unknown>
  on_match: GuardrailAction
}

export interface GuardrailBundle {
  input: GuardrailStep[]
  output: GuardrailStep[]
}

export interface GuardrailPolicy {
  id: string
  name: string
  bundle: GuardrailBundle
}

export interface GuardrailMatch {
  kind: string
  span?: [number, number]
  evidence?: string
}

export interface GuardrailVerdict {
  guardrail: string
  decision: GuardrailAction
  matches: GuardrailMatch[]
  redacted_text: string | null
  reason: string
}

export interface GuardrailTestResult {
  prompt: string
  verdicts: GuardrailVerdict[]
  final_decision: GuardrailAction
}

// ---------- Traces ----------
export type TraceStatus = 'ok' | 'error' | 'blocked' | 'rate_limited' | 'budget_exhausted'

export interface TraceRow {
  id: string
  ts: string
  actor: { user_id?: string | null; key_id?: string | null; org_id: string }
  route: string
  model_requested: string
  model_used: string | null
  provider: string | null
  status: TraceStatus
  latency_ms: number | null
  ttft_ms: number | null
  tokens_in: number | null
  tokens_out: number | null
  tokens_cache_read: number | null
  tokens_cache_write: number | null
  cost_cents: number | null
  cache_hit: boolean
  error: string | null
}

export interface TraceDetail extends TraceRow {
  request_json: unknown
  response_json: unknown
  routing_decision: unknown
  guardrail_verdicts: GuardrailVerdict[]
}

export interface ReplayInput {
  trace_id: string
  override_model?: string | null
  override_policy_id?: string | null
}

// ---------- Playground ----------
export interface PlaygroundSnapshot {
  prompt: string
  system?: string
  model: string
  temperature?: number
  max_tokens?: number
  tools?: unknown[]
}

export interface PlaygroundRunResult {
  model: string
  output: string
  latency_ms: number
  cost_cents: number
  tokens_in: number
  tokens_out: number
  error?: string | null
}

// ---------- Evals ----------
export interface EvalRecord {
  id: string
  input: string
  expected: string
  judge: 'exact' | 'regex' | 'llm' | 'custom'
}

export interface EvalTestSet {
  id: string
  name: string
  records: EvalRecord[]
}

export interface EvalRunRowResult {
  record_id: string
  passed: boolean
  output: string
  latency_ms: number
  cost_cents: number
}

export interface EvalRunSummary {
  target_model: string
  pass_rate: number // 0..1
  p95_latency_ms: number
  total_cost_cents: number
  passed: number
  failed: number
}

export interface EvalRun {
  id: string
  eval_id: string
  target_model: string
  summary: EvalRunSummary
  results: EvalRunRowResult[]
  ran_at: string
}

// ---------- Code snippets ----------
export type SnippetEndpoint =
  | 'openai_chat'
  | 'openai_embeddings'
  | 'anthropic_messages'
  | 'bedrock_converse'
  | 'rerank'
  | 'moderations'

export type SnippetLang = 'curl' | 'python' | 'typescript' | 'claude_code'

export interface SnippetContext {
  endpoint: SnippetEndpoint
  baseUrl: string
  apiKey: string
  model: string
}
