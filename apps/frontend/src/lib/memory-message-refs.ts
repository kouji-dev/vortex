/**
 * Extracts memory ids surfaced on a chat message's `data.memory_ids` payload.
 * Defensive: returns `[]` for any shape the backend has not yet wired.
 */

interface MemoryRefData {
  memory_ids?: unknown
}

export function memoryIdsFromMessage(msg: unknown): string[] {
  if (!msg || typeof msg !== 'object') return []
  const data = (msg as { data?: MemoryRefData }).data
  if (!data || typeof data !== 'object') return []
  const ids = data.memory_ids
  if (!Array.isArray(ids)) return []
  return ids.filter((x): x is string => typeof x === 'string')
}

export function sourceConversationIdFromMessage(msg: unknown): string | null {
  if (!msg || typeof msg !== 'object') return null
  const id = (msg as { conversation_id?: unknown }).conversation_id
  if (typeof id === 'string') return id
  if (typeof id === 'number') return String(id)
  return null
}
