// apps/frontend/src/lib/chat-types.ts
export type ItemKind =
  | "user_message"
  | "assistant_text"
  | "llm_call"
  | "tool_call"
  | "server_tool_use"
  | "thinking"
  | "citation"
  | "memory_pill"
  | "turn_end"
  | "error";

export type ItemStatus = "streaming" | "done" | "error" | "cancelled";
export type ItemRole = "user" | "assistant" | "system";

export interface ThreadItemBase {
  id: number;
  thread_id: number;
  turn_id: string;
  role: ItemRole | null;
  status: ItemStatus;
  provider: string | null;
  model: string | null;
  cost_usd: string | null; // Decimal serialized as string
  cost_estimated: boolean;
  latency_ms: number | null;
  parent_item_id: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface UserMessagePayload { text: string; attachments: unknown[] }
export interface AssistantTextPayload { text: string }
export interface LlmCallPayload {
  input_tokens: number;
  output_tokens: number;
  cached_input_tokens: number;
  cache_creation_input_tokens: number;
  reasoning_tokens: number;
  iteration_index: number;
}
export interface ToolCallPayload {
  tool_name: string;
  params: Record<string, unknown>;
  result_snippet?: string | null;
  error?: string | null;
}
export interface ServerToolUsePayload {
  tool_name: string;
  input: Record<string, unknown>;
}
export interface ThinkingPayload { text: string }
export interface CitationPayload {
  url: string;
  title?: string | null;
  snippet?: string | null;
}
export interface MemoryPillPayload { count: number }
export interface TurnEndPayload { reason: "done" | "error" | "cancelled" }
export interface ErrorPayload { code: string; message: string }

export type ThreadItem =
  | (ThreadItemBase & { kind: "user_message"; data: UserMessagePayload })
  | (ThreadItemBase & { kind: "assistant_text"; data: AssistantTextPayload })
  | (ThreadItemBase & { kind: "llm_call"; data: LlmCallPayload })
  | (ThreadItemBase & { kind: "tool_call"; data: ToolCallPayload })
  | (ThreadItemBase & { kind: "server_tool_use"; data: ServerToolUsePayload })
  | (ThreadItemBase & { kind: "thinking"; data: ThinkingPayload })
  | (ThreadItemBase & { kind: "citation"; data: CitationPayload })
  | (ThreadItemBase & { kind: "memory_pill"; data: MemoryPillPayload })
  | (ThreadItemBase & { kind: "turn_end"; data: TurnEndPayload })
  | (ThreadItemBase & { kind: "error"; data: ErrorPayload });

export type SseEvent =
  | { event_type: "item"; item: ThreadItem }
  | { event_type: "error"; error: ErrorPayload }
  | { event_type: "done" };

export interface ThreadRead {
  id: number;
  org_id: string;
  user_id: number;
  assistant_id: number | null;
  title: string | null;
  model: string | null;
  summary: string | null;
  last_message_at: string | null;
  created_at: string;
}

// ── Legacy conversation types (still needed for conversation metadata) ─────

export type CapabilityKey = "reflection" | "research";
export type CapabilityToggles = Partial<Record<CapabilityKey, boolean>>;

export const DEFAULT_CAPABILITIES: CapabilityToggles = {
  reflection: false,
  research: false,
};

export interface ConversationSettings {
  capabilities?: CapabilityToggles;
  [key: string]: unknown;
}

export interface Conversation {
  id: number;
  org_id: string;
  user_id: number;
  assistant_id: number | null;
  title: string | null;
  model: string | null;
  settings: ConversationSettings | null;
  summary: string | null;
  last_message_at: string | null;
  created_at: string;
  knowledge_base_ids?: number[];
}

export interface UsedKbEntry {
  kb_id: number;
  kb_name: string;
  chunks_used: number;
}

// ── Legacy streaming chip types — used by ThinkingBlock and ThreadItemChip ──
// These are kept for the chip-style streaming UI. New ThreadItem renderer casts
// ThreadItem[] to StreamThreadItem[] when feeding these components.

export type StreamItemStatus = "running" | "done" | "error";

export type StreamThreadItem =
  | { uid: string; kind: "memory"; count: number; status: StreamItemStatus }
  | {
      uid: string;
      kind: "web_search";
      query: string;
      status: StreamItemStatus;
      provider?: string;
      result_snippet?: string;
    }
  | {
      uid: string;
      kind: "fetch_webpage";
      url: string;
      status: StreamItemStatus;
      provider?: string;
      result_snippet?: string;
    }
  | {
      uid: string;
      kind: "kb_search";
      query: string;
      status: StreamItemStatus;
      sources?: { kb_name: string; chunks_used: number }[];
    }
  | {
      uid: string;
      kind: "tool_call";
      tool: string;
      params?: Record<string, string>;
      status: StreamItemStatus;
    };

// ChatMessage is REMOVED — use ThreadItem instead.

// ── Model catalog types (shared by model picker / tuning modal / RBAC panel) ──

export interface CatalogModelRange {
  min: number;
  max: number;
  default: number;
}

export interface CatalogModelReasoning {
  supported: boolean;
  efforts_available: string[];
  default_effort?: string;
}

export interface CatalogModelFeatures {
  vision: boolean;
  tool_use?: boolean;
  [key: string]: unknown;
}

export interface CatalogModelLimits {
  max_input_chars?: number;
  [key: string]: unknown;
}

export interface CatalogModelSampling {
  temperature: CatalogModelRange | null;
  max_output_tokens: CatalogModelRange;
}

export interface CatalogModelSettings {
  reasoning: CatalogModelReasoning;
  features: CatalogModelFeatures;
  sampling: CatalogModelSampling;
  limits?: CatalogModelLimits;
}

export interface CatalogModelEntry {
  id: number;
  slug: string;
  display_name: string;
  description?: string | null;
  api_model_id: string;
  provider: string;
  accessible: boolean;
  is_default: boolean;
  sort_order: number;
  effort: string;
  model_settings: CatalogModelSettings;
  can_request_access?: boolean;
  request_access_url?: string | null;
}
