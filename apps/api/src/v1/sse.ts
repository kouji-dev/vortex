// Minimal SSE line reader — yields raw lines from an upstream byte stream.
// Callers parse `data:` payloads themselves (provider event shapes differ).
export async function* iterSSELines(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<string> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buf.indexOf("\n")) >= 0) {
        yield buf.slice(0, idx);
        buf = buf.slice(idx + 1);
      }
    }
    if (buf.length > 0) yield buf;
  } finally {
    reader.releaseLock();
  }
}

/** Extract the JSON payload of a `data:` SSE line, or null. `[DONE]` → null. */
export function sseData(line: string): string | null {
  const t = line.trim();
  if (!t.startsWith("data:")) return null;
  const data = t.slice(5).trim();
  if (!data || data === "[DONE]") return null;
  return data;
}
