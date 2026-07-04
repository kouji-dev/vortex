import type {
  CanonicalChatRequest,
  OpenAIResponsesRequest,
} from "@vortex/shared";
import type { OpenAIChatCompletion } from "../providers/index.js";
import { iterSSELines, sseData } from "../sse.js";

// OpenAI Responses ⇄ canonical OpenAI-chat. Thin inbound adapter (Codex CLI).

function inputToText(input: unknown): string {
  if (typeof input === "string") return input;
  if (Array.isArray(input))
    return input
      .map((item: any) => {
        if (typeof item === "string") return item;
        if (typeof item?.content === "string") return item.content;
        if (Array.isArray(item?.content))
          return item.content
            .map((c: any) => c?.text ?? "")
            .join("");
        return "";
      })
      .join("\n");
  return "";
}

/** OpenAI Responses request → canonical chat request. */
export function responsesToCanonical(
  req: OpenAIResponsesRequest,
): CanonicalChatRequest {
  const messages: CanonicalChatRequest["messages"] = [];
  const anyReq = req as any;
  if (typeof anyReq.instructions === "string")
    messages.push({ role: "system", content: anyReq.instructions });
  // Array input may already carry role-tagged items; fall back to a single user turn.
  if (Array.isArray(req.input)) {
    for (const item of req.input as any[]) {
      if (item && typeof item === "object" && item.role) {
        messages.push({
          role: item.role,
          content:
            typeof item.content === "string"
              ? item.content
              : inputToText(item.content),
        });
      }
    }
    if (messages.every((m) => m.role === "system"))
      messages.push({ role: "user", content: inputToText(req.input) });
  } else {
    messages.push({ role: "user", content: inputToText(req.input) });
  }
  return {
    model: req.model,
    messages,
    stream: req.stream,
    maxTokens: anyReq.max_output_tokens,
  };
}

/** Canonical (OpenAI chat completion) → OpenAI Responses object. */
export function canonicalToResponses(
  openai: OpenAIChatCompletion,
): Record<string, unknown> {
  const choice = (openai.choices?.[0] ?? {}) as any;
  const text = choice.message?.content ?? "";
  return {
    id: `resp_${openai.id}`,
    object: "response",
    created_at: openai.created,
    model: openai.model,
    status: "completed",
    output: [
      {
        type: "message",
        id: `msg_${openai.id}`,
        status: "completed",
        role: "assistant",
        content: [{ type: "output_text", text, annotations: [] }],
      },
    ],
    output_text: text,
    usage: {
      input_tokens: openai.usage.prompt_tokens,
      output_tokens: openai.usage.completion_tokens,
      total_tokens: openai.usage.total_tokens,
    },
  };
}

/** OpenAI-chat SSE → OpenAI Responses SSE (best-effort delta events). */
export function canonicalStreamToResponses(
  openaiStream: ReadableStream<Uint8Array>,
  model: string,
): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    async start(controller) {
      const enc = new TextEncoder();
      const respId = `resp_${Date.now().toString(36)}`;
      const send = (type: string, data: Record<string, unknown>) =>
        controller.enqueue(
          enc.encode(
            `event: ${type}\ndata: ${JSON.stringify({ type, ...data })}\n\n`,
          ),
        );
      let full = "";
      send("response.created", {
        response: { id: respId, object: "response", model, status: "in_progress" },
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
          const delta = j.choices?.[0]?.delta?.content;
          if (typeof delta === "string" && delta.length) {
            full += delta;
            send("response.output_text.delta", { delta });
          }
        }
      } finally {
        send("response.completed", {
          response: {
            id: respId,
            object: "response",
            model,
            status: "completed",
            output_text: full,
          },
        });
        controller.close();
      }
    },
  });
}
