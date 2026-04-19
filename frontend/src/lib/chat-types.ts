/** Mirrors backend `ConversationRead` / `MessageRead` where the UI needs them. */

export interface UsedKbCitation {
  source: string
  section: string
  page?: number | null
}

export interface UsedKbEntry {
  kb_id: number
  kb_name: string
  chunks_used?: number
  top_score?: number
  /** Section labels from retrieval; omitted in some API / seed payloads. */
  sections?: string[]
  citations?: UsedKbCitation[]
}

export type CapabilityToggles = {
  reflection: boolean
  research: boolean
}

export type ConversationSettings = {
  capabilities?: CapabilityToggles | null
}

export type Conversation = {
  id: number
  user_id: number
  assistant_id: number | null
  title: string | null
  model: string | null
  settings: ConversationSettings | null
  created_at: string
  /** Knowledge bases attached to this thread (RAG scope). */
  knowledge_base_ids: number[]
}

export type MessageUsageExtra = {
  input_tokens?: number
  output_tokens?: number
  cached_input_tokens?: number
  cost_usd?: number | string
  model?: string
}

export type ChatMessage = {
  id: number
  conversation_id: number
  role: string
  content: string
  created_at: string
  extra: (Record<string, unknown> & { usage?: MessageUsageExtra; thinking?: string }) | null
  used_kbs?: UsedKbEntry[] | null
}

/** Router `location.state` — first stream after creating a conversation from the composer. */
export type PendingChatStreamPayload = {
  bootstrapId: string
  content: string
  use_rag: boolean
  model?: string
}

export type AssistantSummary = {
  id: number
  name: string
  description: string
  visibility: string
}

export const DEFAULT_CAPABILITIES: CapabilityToggles = {
  reflection: false,
  research: false,
}

/** Parsed from ``catalog_metadata.config``; stable API surface for UI. */
export type CatalogReasoningSettings = {
  supported: boolean
  efforts_available: string[]
  default_effort: string | null
}

export type CatalogFloatRange = {
  min: number
  max: number
  default: number
}

export type CatalogIntRange = {
  min: number
  max: number
  default: number
}

export type CatalogSamplingSettings = {
  temperature: CatalogFloatRange | null
  max_output_tokens: CatalogIntRange
}

export type CatalogFeatureFlags = {
  streaming: boolean
  vision: boolean
  tools: boolean
  json_mode: boolean
}

export type CatalogLimits = {
  max_input_chars: number
}

export type CatalogModelSettings = {
  reasoning: CatalogReasoningSettings
  sampling: CatalogSamplingSettings
  features: CatalogFeatureFlags
  limits: CatalogLimits
}

/** Mirrors authenticated `GET /api/models` (metadata uses JSON alias). */
export type CatalogModelEntry = {
  id: number
  slug: string
  display_name: string
  description: string
  api_model_id: string
  effort: string
  sort_order: number
  metadata: Record<string, unknown> | null
  model_settings: CatalogModelSettings
  accessible: boolean
  can_request_access: boolean
  request_access_url: string | null
  /** Server default when conversation ``model`` is unset; at most one row per response. */
  is_default?: boolean
}

export type MemoryThreadItem = {
  uid: string
  kind: 'memory'
  count: number
  status: 'running' | 'done'
}

export type WebSearchThreadItem = {
  uid: string
  kind: 'web_search'
  query: string
  result_snippet?: string
  provider?: string
  status: 'running' | 'done'
}

export type KBSearchThreadItem = {
  uid: string
  kind: 'kb_search'
  query: string
  sources?: { kb_name: string; chunks_used: number }[]
  status: 'running' | 'done'
}

export type FetchWebpageThreadItem = {
  uid: string
  kind: 'fetch_webpage'
  url: string
  result_snippet?: string
  provider?: string
  status: 'running' | 'done'
}

export type GenericToolThreadItem = {
  uid: string
  kind: 'tool_call'
  tool: string
  params: Record<string, string>
  status: 'running' | 'done'
}

/** Union of all thread-level stream item types. */
export type StreamThreadItem =
  | MemoryThreadItem
  | WebSearchThreadItem
  | FetchWebpageThreadItem
  | KBSearchThreadItem
  | GenericToolThreadItem
