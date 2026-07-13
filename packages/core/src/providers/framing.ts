// Provider-transport stream framing. Some hosts do not speak plain SSE on the
// wire (AWS Bedrock frames Anthropic events as binary event-stream messages), so
// the transport layer owns decoding/re-framing before the family adapter sees it.

/**
 * Decode an AWS `application/vnd.amazon.eventstream` binary frame stream (used by
 * Bedrock `invoke-with-response-stream`) into the inner JSON chunk objects.
 *
 * Frame layout (big-endian): totalLen(4) headersLen(4) preludeCrc(4)
 * [headers] [payload] messageCrc(4). Bedrock wraps each model chunk as
 * `{"bytes":"<base64 JSON>"}` in the payload, so we base64-decode `bytes`.
 */
export async function* decodeAwsEventStream(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<Record<string, unknown>> {
  const reader = stream.getReader();
  let buf = new Uint8Array(0);
  const append = (chunk: Uint8Array) => {
    const next = new Uint8Array(buf.length + chunk.length);
    next.set(buf);
    next.set(chunk, buf.length);
    buf = next;
  };
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (value) append(value);
      // Drain every complete frame currently buffered.
      while (buf.length >= 12) {
        const view = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
        const totalLen = view.getUint32(0);
        if (totalLen < 16 || totalLen > 16 * 1024 * 1024) break; // guard
        if (buf.length < totalLen) break; // wait for the rest of the frame
        const headersLen = view.getUint32(4);
        const payloadStart = 12 + headersLen;
        const payloadEnd = totalLen - 4;
        const payload = buf.slice(payloadStart, payloadEnd);
        buf = buf.slice(totalLen);
        try {
          const outer = JSON.parse(new TextDecoder().decode(payload));
          const inner =
            typeof outer?.bytes === "string"
              ? JSON.parse(Buffer.from(outer.bytes, "base64").toString("utf8"))
              : outer;
          yield inner as Record<string, unknown>;
        } catch {
          /* skip a frame we can't parse */
        }
      }
      if (done) break;
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Re-frame a Bedrock Anthropic event-stream body into faithful Anthropic SSE
 * (`event:` name + `data:` payload) so the Anthropic family adapter can read it.
 */
export function bedrockAnthropicToSSE(
  body: ReadableStream<Uint8Array>,
): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    async start(controller) {
      const enc = new TextEncoder();
      try {
        for await (const evt of decodeAwsEventStream(body)) {
          const type = (evt as { type?: string }).type ?? "message";
          controller.enqueue(
            enc.encode(`event: ${type}\ndata: ${JSON.stringify(evt)}\n\n`),
          );
        }
      } finally {
        controller.close();
      }
    },
  });
}
