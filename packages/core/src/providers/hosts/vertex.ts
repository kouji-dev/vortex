import { env } from "../../config/env.js";
import type { ModelFamily } from "../catalog.js";
import { BaseProvider, stripTrailingSlash } from "./base.js";
import {
  VERTEX_ANTHROPIC_VERSION,
  type EndpointCtx,
  type ProviderOptions,
} from "./types.js";

// Google Vertex AI. Multi-family: Anthropic (publishers/anthropic + rawPredict)
// + Google (publishers/google + generateContent).
export class VertexProvider extends BaseProvider {
  readonly id = "vertex";
  readonly defaultBaseUrl = "https://aiplatform.googleapis.com";

  override envKey() {
    return env.GOOGLE_VERTEX_API_KEY;
  }
  override envOptions(): ProviderOptions {
    return {
      project: env.GOOGLE_VERTEX_PROJECT,
      region: env.GOOGLE_VERTEX_REGION,
    };
  }
  override adjustBody(body: Record<string, unknown>, family: ModelFamily) {
    if (family === "anthropic") {
      const { model: _m, ...rest } = body;
      return { ...rest, anthropic_version: VERTEX_ANTHROPIC_VERSION };
    }
    return body;
  }

  override resolveEndpoint(ctx: EndpointCtx) {
    const o = ctx.options ?? {};
    const byok = ctx.byokBaseUrl?.trim();
    const project = o.project ?? env.GOOGLE_VERTEX_PROJECT;
    if (!project) throw new Error("vertex: missing project");
    const region = o.region ?? env.GOOGLE_VERTEX_REGION ?? "global";
    const host =
      region === "global"
        ? "https://aiplatform.googleapis.com"
        : `https://${region}-aiplatform.googleapis.com`;
    const base = byok || host;
    const headers: Record<string, string> = { "content-type": "application/json" };
    const apiKeyMode = (o.tokenType ?? "oauth") === "apikey";
    // Claude on Vertex → publishers/anthropic + rawPredict (Anthropic envelope).
    if (ctx.family === "anthropic") {
      const method = ctx.stream ? "streamRawPredict" : "rawPredict";
      let url = `${stripTrailingSlash(base)}/v1/projects/${project}/locations/${region}/publishers/anthropic/models/${ctx.model}:${method}`;
      if (apiKeyMode) url += `?key=${encodeURIComponent(ctx.token)}`;
      else headers.Authorization = `Bearer ${ctx.token}`;
      return { url, headers };
    }
    // Gemini on Vertex → publishers/google + generateContent.
    const method = ctx.stream ? "streamGenerateContent" : "generateContent";
    let url = `${stripTrailingSlash(base)}/v1/projects/${project}/locations/${region}/publishers/google/models/${ctx.model}:${method}`;
    if (apiKeyMode) {
      url += `?key=${encodeURIComponent(ctx.token)}${ctx.stream ? "&alt=sse" : ""}`;
    } else {
      headers.Authorization = `Bearer ${ctx.token}`;
      if (ctx.stream) url += "?alt=sse";
    }
    return { url, headers };
  }
}

export const vertexProvider = new VertexProvider();
