import type { CanonicalChatRequest, Usage } from "@vortex/shared";
import { iterSSELines, sseData } from "../sse.js";
import {
  estTokens,
  newCompletionId,
  type OpenAIChatCompletion,
  type ProviderAdapter,
  type StreamTransformResult,
} from "./types.js";

// Google spoke: canonical OpenAI-chat ↔ Gemini generateContent. Best-effort.
export const googleAdapter: ProviderAdapter = {
  id: "google",
  chatCapability: "chat",

  toProviderBody(req: CanonicalChatRequest, _model, _streaming) {
    const systemParts: string[] = [];
    const contents: Array<{ role: string; parts: Array<{ text: string }> }> = [];
    for (const m of req.messages) {
      const text = typeof m.content === "string" ? m.content : "";
      if (m.role === "system") {
        if (text) systemParts.push(text);
        continue;
      }
      contents.push({
        role: m.role === "assistant" ? "model" : "user",
        parts: [{ text }],
      });
    }
    const generationConfig: Record<string, unknown> = {};
    if (req.maxTokens !== undefined)
      generationConfig.maxOutputTokens = req.maxTokens;
    if (req.temperature !== undefined)
      generationConfig.temperature = req.temperature;
    const body: Record<string, unknown> = { contents };
    if (systemParts.length)
      body.systemInstruction = { parts: [{ text: systemParts.join("\n\n") }] };
    if (Object.keys(generationConfig).length)
      body.generationConfig = generationConfig;
    return body;
  },

  fromProviderResponse(raw, model) {
    const r = (raw ?? {}) as any;
    const text = extractText(r);
    const usage: Usage = {
      promptTokens: r.usageMetadata?.promptTokenCount ?? 0,
      completionTokens: r.usageMetadata?.candidatesTokenCount ?? 0,
      totalTokens:
        r.usageMetadata?.totalTokenCount ??
        (r.usageMetadata?.promptTokenCount ?? 0) +
          (r.usageMetadata?.candidatesTokenCount ?? 0),
    };
    const openai: OpenAIChatCompletion = {
      id: newCompletionId(),
      object: "chat.completion",
      created: Math.floor(Date.now() / 1000),
      model,
      choices: [
        {
          index: 0,
          message: { role: "assistant", content: text },
          finish_reason: "stop",
        },
      ],
      usage: {
        prompt_tokens: usage.promptTokens,
        completion_tokens: usage.completionTokens,
        total_tokens: usage.totalTokens,
      },
    };
    return { openai, usage };
  },

  streamTransform(upstream, model): StreamTransformResult {
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
        const emit = (delta: object, finish: string | null = null) =>
          controller.enqueue(
            enc.encode(
              `data: ${JSON.stringify({
                id,
                object: "chat.completion.chunk",
                created: Math.floor(Date.now() / 1000),
                model,
                choices: [{ index: 0, delta, finish_reason: finish }],
              })}\n\n`,
            ),
          );
        emit({ role: "assistant", content: "" });
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
            const text = extractText(ev);
            if (text) {
              completionChars += text.length;
              emit({ content: text });
            }
            if (ev.usageMetadata) {
              promptTokens = ev.usageMetadata.promptTokenCount ?? promptTokens;
              completionTokens =
                ev.usageMetadata.candidatesTokenCount ?? completionTokens;
            }
          }
        } finally {
          // Resolve usage BEFORE controller ops (which may throw when the
          // stream was cancelled) so finalize always fires downstream.
          const estimated = completionTokens === 0;
          const out = completionTokens || estTokens(completionChars);
          done({
            promptTokens,
            completionTokens: out,
            totalTokens: promptTokens + out,
            isEstimated: estimated,
          });
          try {
            emit({}, "stop");
            controller.enqueue(enc.encode("data: [DONE]\n\n"));
            controller.close();
          } catch {
            /* already cancelled/errored */
          }
        }
      },
    });

    return { stream, usage };
  },
};

function extractText(r: any): string {
  const parts = r?.candidates?.[0]?.content?.parts;
  if (!Array.isArray(parts)) return "";
  return parts.map((p: any) => p?.text ?? "").join("");
}
