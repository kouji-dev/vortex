import { env } from "../config/env.js";

export type Capability =
  | "chat"
  | "messages"
  | "responses"
  | "embeddings"
  | "models";

export type AuthStyle = "bearer" | "x-api-key" | "query";

export interface ProviderDef {
  /** Stable provider id (matches ENABLED_PROVIDERS + DB provider column). */
  id: string;
  /** Default upstream base URL (no trailing slash). */
  defaultBaseUrl: string;
  /** How credentials are attached to the upstream request. */
  authStyle: AuthStyle;
  /**
   * Path (relative to base URL) for a capability + streaming variant.
   * Throws for capabilities the provider does not serve natively.
   * Google paths carry a `{model}` placeholder the caller/transform fills.
   */
  endpointFor(capability: Capability, streaming: boolean): string;
  /**
   * Auth headers for the upstream request. For `query`-style providers the
   * token travels in the URL, so this returns non-secret headers only.
   */
  authHeaders(token: string): Record<string, string>;
}

const openai: ProviderDef = {
  id: "openai",
  defaultBaseUrl: "https://api.openai.com",
  authStyle: "bearer",
  endpointFor(capability) {
    switch (capability) {
      case "chat":
        return "/v1/chat/completions";
      case "responses":
        return "/v1/responses";
      case "embeddings":
        return "/v1/embeddings";
      case "models":
        return "/v1/models";
      default:
        throw new Error(`openai: unsupported capability '${capability}'`);
    }
  },
  authHeaders(token) {
    return { Authorization: `Bearer ${token}` };
  },
};

const anthropic: ProviderDef = {
  id: "anthropic",
  defaultBaseUrl: "https://api.anthropic.com",
  authStyle: "x-api-key",
  endpointFor(capability) {
    switch (capability) {
      case "messages":
        return "/v1/messages";
      case "models":
        return "/v1/models";
      default:
        throw new Error(`anthropic: unsupported capability '${capability}'`);
    }
  },
  authHeaders(token) {
    return { "x-api-key": token, "anthropic-version": "2023-06-01" };
  },
};

const google: ProviderDef = {
  id: "google",
  defaultBaseUrl: "https://generativelanguage.googleapis.com",
  authStyle: "query",
  endpointFor(capability, streaming) {
    switch (capability) {
      case "chat":
        return streaming
          ? "/v1beta/models/{model}:streamGenerateContent"
          : "/v1beta/models/{model}:generateContent";
      case "embeddings":
        return "/v1beta/models/{model}:embedContent";
      case "models":
        return "/v1beta/models";
      default:
        throw new Error(`google: unsupported capability '${capability}'`);
    }
  },
  // Google auth key is passed as a `?key=` query param by the caller.
  authHeaders() {
    return {};
  },
};

// Deployment-specific providers. Their base URL/path need per-credential
// options (resource/deployment/region/project); real construction lives in
// `resolveEndpoint`, so `endpointFor` is unused for them.
const azure: ProviderDef = {
  id: "azure",
  defaultBaseUrl: "https://RESOURCE.openai.azure.com",
  authStyle: "x-api-key",
  endpointFor() {
    throw new Error("azure: use resolveEndpoint");
  },
  authHeaders(token) {
    return { "api-key": token };
  },
};

const bedrock: ProviderDef = {
  id: "bedrock",
  defaultBaseUrl: "https://bedrock-runtime.us-east-1.amazonaws.com",
  authStyle: "bearer", // Bedrock now takes a bearer API key (no SigV4)
  endpointFor() {
    throw new Error("bedrock: use resolveEndpoint");
  },
  authHeaders(token) {
    return { Authorization: `Bearer ${token}` };
  },
};

const vertex: ProviderDef = {
  id: "vertex",
  defaultBaseUrl: "https://aiplatform.googleapis.com",
  authStyle: "bearer",
  endpointFor() {
    throw new Error("vertex: use resolveEndpoint");
  },
  authHeaders(token) {
    return { Authorization: `Bearer ${token}` };
  },
};

const REGISTRY: Record<string, ProviderDef> = {
  openai,
  anthropic,
  google,
  azure,
  bedrock,
  vertex,
};

// Per-provider env base-URL override (empty string treated as unset).
const ENV_BASE_URL: Record<string, string | undefined> = {
  openai: env.OPENAI_BASE_URL,
  anthropic: env.ANTHROPIC_BASE_URL,
  google: env.GOOGLE_BASE_URL,
  bedrock: env.AWS_BEDROCK_BASE_URL,
};

/** Look up a provider definition by id, or `undefined` if unknown. */
export function getProvider(id: string): ProviderDef | undefined {
  return REGISTRY[id];
}

function stripTrailingSlash(url: string): string {
  return url.replace(/\/+$/, "");
}

/**
 * Resolve the effective base URL for a provider.
 * Precedence: BYOK cred baseUrl > env override > provider default.
 */
export function resolveBaseUrl(
  provider: ProviderDef,
  opts: { byokBaseUrl?: string | null } = {},
): string {
  const byok = opts.byokBaseUrl?.trim();
  if (byok) return stripTrailingSlash(byok);
  const override = ENV_BASE_URL[provider.id]?.trim();
  if (override) return stripTrailingSlash(override);
  return stripTrailingSlash(provider.defaultBaseUrl);
}

/**
 * Providers available for this deployment = code catalog ∩ ENABLED_PROVIDERS.
 * An empty ENABLED_PROVIDERS means "all providers in the code catalog".
 */
export function listEnabledProviders(): ProviderDef[] {
  const enabled = env.ENABLED_PROVIDERS;
  if (enabled.length === 0) return Object.values(REGISTRY);
  return enabled
    .map((id) => REGISTRY[id])
    .filter((p): p is ProviderDef => p !== undefined);
}

/** BYOK / deployment options stored per provider credential (or from env). */
export interface ProviderOptions {
  azureResource?: string;
  azureApiVersion?: string;
  deployment?: string; // Azure deployment name (defaults to the model)
  region?: string; // Bedrock / Vertex region
  project?: string; // Vertex GCP project
  tokenType?: "oauth" | "apikey"; // Vertex auth mode
}

export interface EndpointCtx {
  token: string;
  model: string;
  capability: Capability;
  stream: boolean;
  options?: ProviderOptions | null;
  byokBaseUrl?: string | null;
}

/**
 * Build the upstream `{ url, headers }` for any provider. Standard providers
 * (openai/anthropic/google) reproduce the default behavior exactly; azure /
 * bedrock / vertex construct deployment-specific endpoints from options.
 */
export function resolveEndpoint(
  providerId: string,
  ctx: EndpointCtx,
): { url: string; headers: Record<string, string> } {
  const o = ctx.options ?? {};
  const byok = ctx.byokBaseUrl?.trim();

  if (providerId === "azure") {
    const resource = o.azureResource ?? env.AZURE_OPENAI_RESOURCE;
    if (!resource) throw new Error("azure: missing resource");
    const apiVersion =
      o.azureApiVersion ?? env.AZURE_OPENAI_API_VERSION ?? "2024-10-21";
    const deployment = o.deployment ?? ctx.model;
    const base = byok || `https://${resource}.openai.azure.com`;
    const kind = ctx.capability === "embeddings" ? "embeddings" : "chat/completions";
    return {
      url: `${stripTrailingSlash(base)}/openai/deployments/${deployment}/${kind}?api-version=${apiVersion}`,
      headers: { "content-type": "application/json", "api-key": ctx.token },
    };
  }

  if (providerId === "bedrock") {
    const region = o.region ?? env.AWS_BEDROCK_REGION ?? "us-east-1";
    const base =
      byok ||
      env.AWS_BEDROCK_BASE_URL?.trim() ||
      `https://bedrock-runtime.${region}.amazonaws.com`;
    // OpenAI-compatible mantle path + bearer key
    return {
      url: `${stripTrailingSlash(base)}/openai/v1/chat/completions`,
      headers: {
        "content-type": "application/json",
        Authorization: `Bearer ${ctx.token}`,
      },
    };
  }

  if (providerId === "vertex") {
    const project = o.project ?? env.GOOGLE_VERTEX_PROJECT;
    if (!project) throw new Error("vertex: missing project");
    const region = o.region ?? env.GOOGLE_VERTEX_REGION ?? "global";
    const host =
      region === "global"
        ? "https://aiplatform.googleapis.com"
        : `https://${region}-aiplatform.googleapis.com`;
    const base = byok || host;
    const method = ctx.stream ? "streamGenerateContent" : "generateContent";
    let url = `${stripTrailingSlash(base)}/v1/projects/${project}/locations/${region}/publishers/google/models/${ctx.model}:${method}`;
    const headers: Record<string, string> = { "content-type": "application/json" };
    if ((o.tokenType ?? "oauth") === "apikey") {
      url += `?key=${encodeURIComponent(ctx.token)}${ctx.stream ? "&alt=sse" : ""}`;
    } else {
      headers.Authorization = `Bearer ${ctx.token}`;
      if (ctx.stream) url += "?alt=sse";
    }
    return { url, headers };
  }

  // standard providers
  const def = getProvider(providerId);
  if (!def) throw new Error(`unknown provider '${providerId}'`);
  const base = resolveBaseUrl(def, { byokBaseUrl: ctx.byokBaseUrl });
  let url =
    base + def.endpointFor(ctx.capability, ctx.stream).replace("{model}", ctx.model);
  const headers: Record<string, string> = {
    "content-type": "application/json",
    ...def.authHeaders(ctx.token),
  };
  if (def.authStyle === "query") {
    const sep = url.includes("?") ? "&" : "?";
    url += `${sep}key=${encodeURIComponent(ctx.token)}`;
    if (ctx.stream) url += "&alt=sse";
  }
  return { url, headers };
}
