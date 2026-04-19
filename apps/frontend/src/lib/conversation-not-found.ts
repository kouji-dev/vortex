/** Detects GET /conversations/:id 404 body from FastAPI (`{ "detail": "…" }` or plain text). */
export function isConversationNotFoundError(message: string): boolean {
  const m = message.trim()
  if (/conversation not found/i.test(m)) return true
  try {
    const j = JSON.parse(m) as { detail?: unknown }
    if (typeof j.detail === 'string' && /conversation not found/i.test(j.detail)) {
      return true
    }
    if (Array.isArray(j.detail)) {
      return j.detail.some(
        (d) => typeof d === 'string' && /conversation not found/i.test(d),
      )
    }
  } catch {
    /* not JSON */
  }
  return false
}
