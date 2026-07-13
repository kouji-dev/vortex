import type {
  AnthropicMessagesRequest,
  CanonicalChatRequest,
} from "@vortex/shared";
import { iterSSELines, sseData, type OpenAIChatCompletion } from "@vortex/core";

// Anthropic Messages ⇄ canonical OpenAI-chat. Inbound thin adapter: validate
// native → transcode to canonical → run the ONE core handler → transcode back.

function blocksToText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content))
    return content
      .map((b: any) => (b?.type === "text" ? b.text : ""))
      .join("");
  return "";
}

/** Anthropic Messages request → canonical chat request. */
export function messagesToCanonical(
  req: AnthropicMessagesRequest,
): CanonicalChatRequest {
  const messages: CanonicalChatRequest["messages"] = [];
  if (req.system) {
    messages.push({ role: "system", content: blocksToText(req.system) });
  }
  for (const m of req.messages as Array<{ role: string; content: unknown }>) {
    messages.push({
      role: m.role,
      content:
        typeof m.content === "string" ? m.content : blocksToText(m.content),
    });
  }
  return {
    model: req.model,
    messages,
    stream: req.stream,
    maxTokens: req.max_tokens,
  };
}

function mapFinishToStop(reason: unknown): string {
  switch (reason) {
    case "length":
      return "max_tokens";
    case "tool_calls":
      return "tool_use";
    default:
      return "end_turn";
  }
}

/** Canonical (OpenAI chat completion) → Anthropic Messages response. */
export function canonicalToMessagesResponse(
  openai: OpenAIChatCompletion,
): Record<string, unknown> {
  const choice = (openai.choices?.[0] ?? {}) as any;
  const text = choice.message?.content ?? "";
  return {
    id: openai.id,
    type: "message",
    role: "assistant",
    model: openai.model,
    content: [{ type: "text", text }],
    stop_reason: mapFinishToStop(choice.finish_reason),
    stop_sequence: null,
    usage: {
      input_tokens: openai.usage.prompt_tokens,
      output_tokens: openai.usage.completion_tokens,
    },
  };
}

/** OpenAI-chat SSE → Anthropic Messages SSE (best-effort). */
export function canonicalStreamToMessages(
  openaiStream: ReadableStream<Uint8Array>,
  model: string,
): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    async start(controller) {
      const enc = new TextEncoder();
      const msgId = `msg_${Date.now().toString(36)}`;
      let outputTokens = 0;
      let promptTokens = 0;
      const send = (event: string, data: unknown) =>
        controller.enqueue(
          enc.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`),
        );

      send("message_start", {
        type: "message_start",
        message: {
          id: msgId,
          type: "message",
          role: "assistant",
          model,
          content: [],
          stop_reason: null,
          usage: { input_tokens: 0, output_tokens: 0 },
        },
      });
      send("content_block_start", {
        type: "content_block_start",
        index: 0,
        content_block: { type: "text", text: "" },
      });

      try {
        for await (const line of iterSSELines(openaiStream)) {
          const data = sseData(line);
          if (!data) continue;
          let j: any;
          try {
            j = JSON.parse(data);
          } catch {
            continue;
          }
          if (j.usage) {
            promptTokens = j.usage.prompt_tokens ?? promptTokens;
            outputTokens = j.usage.completion_tokens ?? outputTokens;
          }
          const delta = j.choices?.[0]?.delta?.content;
          if (typeof delta === "string" && delta.length) {
            outputTokens += 0;
            send("content_block_delta", {
              type: "content_block_delta",
              index: 0,
              delta: { type: "text_delta", text: delta },
            });
          }
        }
      } finally {
        send("content_block_stop", { type: "content_block_stop", index: 0 });
        send("message_delta", {
          type: "message_delta",
          delta: { stop_reason: "end_turn" },
          usage: { input_tokens: promptTokens, output_tokens: outputTokens },
        });
        send("message_stop", { type: "message_stop" });
        controller.close();
      }
    },
  });
}
