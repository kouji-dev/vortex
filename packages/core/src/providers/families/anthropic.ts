import type { CanonicalChatRequest, Usage } from "@vortex/shared";
import type { Capability } from "../hosts/types.js";
import { iterSSELines, sseData } from "../sse.js";
import {
  estTokens,
  newCompletionId,
  sniffSSE,
  type OpenAIChatCompletion,
  type FamilyAdapter,
  type StreamTransformResult,
} from "./types.js";

// Anthropic spoke: canonical OpenAI-chat ↔ Anthropic Messages.
export class AnthropicFamilyAdapter implements FamilyAdapter {
  readonly id = "anthropic";
  readonly chatCapability: Capability = "messages";

  toProviderBody(req: CanonicalChatRequest, model: string, streaming: boolean) {
    const systemParts: string[] = [];
    const messages: Array<{ role: string; content: unknown }> = [];
    for (const m of req.messages) {
      if (m.role === "system") {
        if (typeof m.content === "string") systemParts.push(m.content);
        continue;
      }
      messages.push({
        role: m.role === "assistant" ? "assistant" : "user",
        content: m.content ?? "",
      });
    }
    const body: Record<string, unknown> = {
      model,
      // Anthropic requires max_tokens; pick a sane default when absent.
      max_tokens: req.maxTokens ?? 1024,
      messages,
    };
    if (systemParts.length) body.system = systemParts.join("\n\n");
    if (req.temperature !== undefined) body.temperature = req.temperature;
    if (req.tools !== undefined) body.tools = req.tools;
    if (streaming) body.stream = true;
    return body;
  }

  fromProviderResponse(raw: unknown, model: string) {
    const r = (raw ?? {}) as any;
    const text = Array.isArray(r.content)
      ? r.content
          .filter((b: any) => b?.type === "text")
          .map((b: any) => b.text)
          .join("")
      : "";
    const usage: Usage = {
      promptTokens: r.usage?.input_tokens ?? 0,
      completionTokens: r.usage?.output_tokens ?? 0,
      totalTokens: (r.usage?.input_tokens ?? 0) + (r.usage?.output_tokens ?? 0),
    };
    const openai: OpenAIChatCompletion = {
      id: r.id ?? newCompletionId(),
      object: "chat.completion",
      created: Math.floor(Date.now() / 1000),
      model,
      choices: [
        {
          index: 0,
          message: { role: "assistant", content: text },
          finish_reason: mapStop(r.stop_reason),
        },
      ],
      usage: {
        prompt_tokens: usage.promptTokens,
        completion_tokens: usage.completionTokens,
        total_tokens: usage.totalTokens,
      },
    };
    return { openai, usage };
  }

  streamTransform(
    upstream: ReadableStream<Uint8Array>,
    model: string,
  ): StreamTransformResult {
    let resolve!: (u: Usage) => void;
    const usage = new Promise<Usage>((r) => (resolve = r));
    let settled = false;
    let promptTokens = 0;
    let completionTokens = 0;
    let completionChars = 0;
    const id = newCompletionId();
    const done = (u: Usage) => {
      if (settled) return;
      settled = true;
      resolve(u);
    };

    const stream = new ReadableStream<Uint8Array>({
      async start(controller) {
        const enc = new TextEncoder();
        const emit = (obj: unknown) =>
          controller.enqueue(enc.encode(`data: ${JSON.stringify(obj)}\n\n`));
        const chunk = (delta: object, finish: string | null = null) => ({
          id,
          object: "chat.completion.chunk",
          created: Math.floor(Date.now() / 1000),
          model,
          choices: [{ index: 0, delta, finish_reason: finish }],
        });
        try {
          for await (const line of iterSSELines(upstream)) {
            const data = sseData(line);
            if (!data) continue;
            let ev: any;
            try {
              ev = JSON.parse(data);
            } catch {
              continue;
            }
            switch (ev.type) {
              case "message_start":
                promptTokens = ev.message?.usage?.input_tokens ?? 0;
                emit(chunk({ role: "assistant", content: "" }));
                break;
              case "content_block_delta": {
                const text = ev.delta?.text ?? "";
                if (text) {
                  completionChars += text.length;
                  emit(chunk({ content: text }));
                }
                break;
              }
              case "message_delta":
                if (ev.usage?.output_tokens != null)
                  completionTokens = ev.usage.output_tokens;
                break;
              case "message_stop":
                emit(chunk({}, "stop"));
                break;
              default:
                break;
            }
          }
        } finally {
          controller.enqueue(enc.encode("data: [DONE]\n\n"));
          const out = completionTokens || estTokens(completionChars);
          done({
            promptTokens,
            completionTokens: out,
            totalTokens: promptTokens + out,
          });
          controller.close();
        }
      },
    });

    return { stream, usage };
  }

  parseUsage(raw: unknown): Usage {
    const u = ((raw ?? {}) as any).usage ?? {};
    const p = u.input_tokens ?? 0;
    const c = u.output_tokens ?? 0;
    return { promptTokens: p, completionTokens: c, totalTokens: p + c };
  }

  sniffStreamUsage(stream: ReadableStream<Uint8Array>): Promise<Usage> {
    return sniffSSE(stream, (j, acc) => {
      if (j.type === "message_start")
        acc.prompt = j.message?.usage?.input_tokens ?? acc.prompt;
      if (j.type === "message_delta") {
        if (j.usage?.input_tokens != null) acc.prompt = j.usage.input_tokens;
        if (j.usage?.output_tokens != null) acc.completion = j.usage.output_tokens;
      }
    });
  }
}

export const anthropicAdapter = new AnthropicFamilyAdapter();

function mapStop(reason: string | undefined): string {
  switch (reason) {
    case "max_tokens":
      return "length";
    case "tool_use":
      return "tool_calls";
    default:
      return "stop";
  }
}
