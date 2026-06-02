export type WorkerRuntime = 'claude' | 'codex'

/** Derive the agent runtime from a model id; null if the model can't drive a CLI. */
export function inferRuntime(apiModelId: string): WorkerRuntime | null {
  const id = apiModelId.toLowerCase()
  if (id.startsWith('claude-')) return 'claude'
  if (id.includes('codex')) return 'codex'
  return null
}
