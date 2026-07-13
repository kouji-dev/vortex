import type { Capability } from "../hosts/types.js";
import type { CanonicalChatRequest, Usage } from "@vortex/shared";
import { iterSSELines, sseData } from "../sse.js";
import {
  estTokens,
  sniffSSE,
  type OpenAIChatCompletion,
  type FamilyAdapter,
  type StreamTransformResult,
} from "./types.js";

// OpenAI is the canonical format → this adapter is (almost) a passthrough.
export class OpenAIFamilyAdapter implements FamilyAdapter {
  readonly id = "openai";
  readonly chatCapability: Capability = "chat";

  toProviderBody(req: CanonicalChatRequest, model: string, streaming: boolean) {
    const body: Record<string, unknown> = {
      model,
      messages: req.messages,
    };
    if (req.temperature !== undefined) body.temperature = req.temperature;
    if (req.maxTokens !== undefined) body.max_tokens = req.maxTokens;
    if (req.tools !== undefined) body.tools = req.tools;
    if (streaming) {
      body.stream = true;
      // Force a trailing usage chunk so we can meter streamed responses.
      body.stream_options = { include_usage: true };
    }
    return body;
  }

  fromProviderResponse(raw: unknown, model: string) {
    const r = (raw ?? {}) as Record<string, unknown>;
    const u = (r.usage ?? {}) as Record<string, number>;
    const usage: Usage = {
      promptTokens: u.prompt_tokens ?? 0,
      completionTokens: u.completion_tokens ?? 0,
      totalTokens:
        u.total_tokens ?? (u.prompt_tokens ?? 0) + (u.completion_tokens ?? 0),
    };
    return { openai: { ...(r as object), model } as OpenAIChatCompletion, usage };
  }

  streamTransform(
    upstream: ReadableStream<Uint8Array>,
    _model: string,
  ): StreamTransformResult {
    let resolve!: (u: Usage) => void;
    const usage = new Promise<Usage>((r) => (resolve = r));
    let settled = false;
    let promptTokens = 0;
    let completionChars = 0;
    const done = (u: Usage) => {
      if (settled) return;
      settled = true;
      resolve(u);
    };

    const stream = new ReadableStream<Uint8Array>({
      async start(controller) {
        const enc = new TextEncoder();
        try {
          for await (const line of iterSSELines(upstream)) {
            controller.enqueue(enc.encode(line + "\n"));
            const data = sseData(line);
            if (!data) continue;
            try {
              const j = JSON.parse(data) as any;
              if (j.usage) {
                promptTokens = j.usage.prompt_tokens ?? 0;
                done({
                  promptTokens,
                  completionTokens: j.usage.completion_tokens ?? 0,
                  totalTokens:
                    j.usage.total_tokens ??
                    (j.usage.prompt_tokens ?? 0) +
                      (j.usage.completion_tokens ?? 0),
                  isEstimated: false,
                });
              }
              const delta = j.choices?.[0]?.delta?.content;
              if (typeof delta === "string") completionChars += delta.length;
            } catch {
              /* ignore malformed chunk */
            }
          }
        } finally {
          // Fallback when no usage chunk arrived: chars/4 estimate. `done` is
          // resolved BEFORE any controller op so finalize always fires, and
          // close is guarded — the stream may already be cancelled/errored.
          const est = estTokens(completionChars);
          done({
            promptTokens,
            completionTokens: est,
            totalTokens: promptTokens + est,
            isEstimated: true,
          });
          try {
            controller.close();
          } catch {
            /* already cancelled/errored */
          }
        }
      },
    });

    return { stream, usage };
  }

  parseUsage(raw: unknown, capability: Capability): Usage {
    const j = (raw ?? {}) as any;
    const u = j.usage ?? {};
    if (capability === "responses") {
      const p = u.input_tokens ?? 0;
      const c = u.output_tokens ?? 0;
      return { promptTokens: p, completionTokens: c, totalTokens: u.total_tokens ?? p + c };
    }
    const p = u.prompt_tokens ?? 0;
    const c = u.completion_tokens ?? 0;
    return { promptTokens: p, completionTokens: c, totalTokens: u.total_tokens ?? p + c };
  }

  sniffStreamUsage(
    stream: ReadableStream<Uint8Array>,
    capability: Capability,
  ): Promise<Usage> {
    return sniffSSE(stream, (j, acc) => {
      if (capability === "responses") {
        const u = j.response?.usage ?? j.usage;
        if (u) {
          acc.prompt = u.input_tokens ?? acc.prompt;
          acc.completion = u.output_tokens ?? acc.completion;
        }
      } else if (j.usage) {
        acc.prompt = j.usage.prompt_tokens ?? acc.prompt;
        acc.completion = j.usage.completion_tokens ?? acc.completion;
      }
    });
  }
}

export const openaiAdapter = new OpenAIFamilyAdapter();
