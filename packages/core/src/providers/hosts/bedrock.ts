import { env } from "../../config/env.js";
import type { ModelFamily } from "../catalog.js";
import { bedrockAnthropicToSSE } from "../framing.js";
import { BaseProvider, stripTrailingSlash } from "./base.js";
import {
  BEDROCK_ANTHROPIC_VERSION,
  type EndpointCtx,
  type ProviderOptions,
} from "./types.js";

// AWS Bedrock (bearer key). Multi-family: Anthropic (native invoke) + OpenAI
// (OSS mantle). Region-prefixes the model id and re-frames the event-stream.
export class BedrockProvider extends BaseProvider {
  readonly id = "bedrock";
  readonly defaultBaseUrl = "https://bedrock-runtime.us-east-1.amazonaws.com";

  override envKey() {
    return env.AWS_BEDROCK_API_KEY;
  }
  override envOptions(): ProviderOptions {
    return { region: env.AWS_BEDROCK_REGION };
  }
  // Claude on Bedrock: model travels in the URL; body carries anthropic_version.
  override adjustBody(body: Record<string, unknown>, family: ModelFamily) {
    if (family === "anthropic") {
      const { model: _m, ...rest } = body;
      return { ...rest, anthropic_version: BEDROCK_ANTHROPIC_VERSION };
    }
    return body;
  }
  // Bedrock emits Anthropic events as AWS event-stream binary frames → SSE.
  override wrapStream(body: ReadableStream<Uint8Array>, family: ModelFamily) {
    return family === "anthropic" ? bedrockAnthropicToSSE(body) : body;
  }

  override resolveEndpoint(ctx: EndpointCtx) {
    const o = ctx.options ?? {};
    const byok = ctx.byokBaseUrl?.trim();
    const region = o.region ?? env.AWS_BEDROCK_REGION ?? "us-east-1";
    const base =
      byok ||
      env.AWS_BEDROCK_BASE_URL?.trim() ||
      `https://bedrock-runtime.${region}.amazonaws.com`;
    const headers: Record<string, string> = {
      "content-type": "application/json",
      Authorization: `Bearer ${ctx.token}`, // Bedrock bearer API key (no SigV4)
    };
    // Claude on Bedrock → native invoke endpoint (Anthropic Messages envelope +
    // AWS event-stream framing on the streaming variant). ctx.model is the
    // region-prefixed model id (e.g. `us.anthropic.claude-…-v1:0`).
    if (ctx.family === "anthropic") {
      const path = ctx.stream
        ? `/model/${encodeURIComponent(ctx.model)}/invoke-with-response-stream`
        : `/model/${encodeURIComponent(ctx.model)}/invoke`;
      return { url: `${stripTrailingSlash(base)}${path}`, headers };
    }
    // OpenAI-compatible mantle path for OSS/OpenAI-family models.
    return {
      url: `${stripTrailingSlash(base)}/openai/v1/chat/completions`,
      headers,
    };
  }
}

export const bedrockProvider = new BedrockProvider();
