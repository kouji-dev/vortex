/** Mirrors authenticated knowledge-base API responses. */

export type KnowledgeBaseSummary = {
  id: number
  name: string
  description: string
  owner_user_id: number
  created_at: string
  /** Returned by the API when the backend includes it; may be absent. */
  document_count?: number
  /** Sum of chunks_total across docs (if available). */
  chunks_count?: number
  /** Total byte size across stored files (if available). */
  size_bytes?: number
}

export type KnowledgeBaseDocument = {
  id: number
  knowledge_base_id: number
  filename: string
  status: string
  /** Present when ingest failed (embedding API, etc.). */
  ingest_error?: string | null
  created_at: string
}

export const CONNECTOR_KINDS = [
  'files',
  'github',
  'gitlab',
  'confluence',
  's3',
] as const

export type ConnectorKind = (typeof CONNECTOR_KINDS)[number]

export const CONNECTOR_KIND_LABELS: Record<ConnectorKind, string> = {
  files: 'Files (manual upload)',
  github: 'GitHub',
  gitlab: 'GitLab',
  confluence: 'Confluence',
  s3: 'Amazon S3',
}

/** Kinds with real sync/upload behavior; others stay disabled in UI until implemented. */
export const CONNECTOR_KINDS_IMPLEMENTED: ReadonlySet<ConnectorKind> = new Set(['files'])

export function isConnectorKindImplemented(kind: ConnectorKind): boolean {
  return CONNECTOR_KINDS_IMPLEMENTED.has(kind)
}

export type KnowledgeBaseConnector = {
  id: number
  knowledge_base_id: number
  kind: ConnectorKind | string
  label: string
  settings: Record<string, unknown>
  enabled: boolean
  created_at: string
}

export type ConnectorSyncJob = {
  id: number
  knowledge_base_id: number
  connector_id: number
  job_type: string
  status: string
  error_message: string | null
  meta: Record<string, unknown>
  created_at: string
  started_at: string | null
  finished_at: string | null
}

function tryParseFastApiDetail(text: string): string | undefined {
  const trimmed = text.trim()
  if (!trimmed) return undefined
  try {
    const j = JSON.parse(trimmed) as { detail?: unknown }
    if (typeof j.detail === 'string') return j.detail
  } catch {
    return undefined
  }
  return undefined
}

/** True when FastAPI returns its default unmatched-route 404 (not e.g. `Knowledge base not found`). */
export function isFastApiGenericNotFoundResponse(res: Response, text: string): boolean {
  if (res.status !== 404) return false
  return tryParseFastApiDetail(text) === 'Not Found'
}

/**
 * List GETs: success → parsed array. Generic FastAPI 404 (`{"detail":"Not Found"}`) → `[]`
 * so the UI shows an empty state instead of raw JSON (e.g. old proxy or route not mounted).
 * Other 404s (e.g. `Knowledge base not found`) still throw.
 */
export function knowledgeBaseListFromResponse<T>(
  res: Response,
  text: string,
  parseBody: (body: string) => T[],
): T[] {
  if (res.ok) return parseBody(text)
  if (res.status === 404) {
    const detail = tryParseFastApiDetail(text)
    if (detail === 'Not Found') return []
  }
  throw new Error(text || res.statusText)
}

/** Successful GET list: empty body or `null` → [] (no React Query JSON parse error). */
export function parseKnowledgeBasesListJson(text: string): KnowledgeBaseSummary[] {
  const trimmed = text.trim()
  if (!trimmed) return []
  const data: unknown = JSON.parse(trimmed)
  return Array.isArray(data) ? (data as KnowledgeBaseSummary[]) : []
}

export function parseKnowledgeBaseDocumentsListJson(text: string): KnowledgeBaseDocument[] {
  const trimmed = text.trim()
  if (!trimmed) return []
  const data: unknown = JSON.parse(trimmed)
  return Array.isArray(data) ? (data as KnowledgeBaseDocument[]) : []
}

export function parseKnowledgeBaseConnectorsListJson(text: string): KnowledgeBaseConnector[] {
  const trimmed = text.trim()
  if (!trimmed) return []
  const data: unknown = JSON.parse(trimmed)
  return Array.isArray(data) ? (data as KnowledgeBaseConnector[]) : []
}

export function parseConnectorSyncJobsListJson(text: string): ConnectorSyncJob[] {
  const trimmed = text.trim()
  if (!trimmed) return []
  const data: unknown = JSON.parse(trimmed)
  return Array.isArray(data) ? (data as ConnectorSyncJob[]) : []
}
