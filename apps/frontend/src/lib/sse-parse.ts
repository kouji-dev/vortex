export function parseSseBlocks(buffer: string): { events: unknown[]; rest: string } {
  const events: unknown[] = []
  const parts = buffer.split('\n\n')
  const rest = parts.pop() ?? ''
  for (const block of parts) {
    const line = block.startsWith('data: ') ? block.slice(6).trim() : block.trim()
    if (!line) continue
    try {
      events.push(JSON.parse(line))
    } catch {
      /* ignore */
    }
  }
  return { events, rest }
}
