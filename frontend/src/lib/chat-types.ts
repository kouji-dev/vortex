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
  web: boolean
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

export type ChatMessage = {
  id: number
  conversation_id: number
  role: string
  content: string
  created_at: string
  extra: Record<string, unknown> | null
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
  web: false,
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

export type ToolCallItem = {
  kind: 'tool_call'
  tool: string
  params: Record<string, string>
  status: 'running' | 'done'
}

export type MemoryItem = {
  kind: 'memory'
  count: number
  status: 'running' | 'done'
}

export type ThinkingChildItem = ToolCallItem | MemoryItem

export type ThinkingItem = {
  kind: 'thinking'
  status: 'running' | 'done'
  children: ThinkingChildItem[]
}

export type StreamItem = ThinkingItem | ThinkingChildItem
