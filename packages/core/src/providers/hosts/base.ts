import type { ModelFamily } from "../catalog.js";
import type {
  AuthStyle,
  Capability,
  EndpointCtx,
  ProviderAdapter,
  ProviderOptions,
} from "./types.js";

export function stripTrailingSlash(url: string): string {
  return url.replace(/\/+$/, "");
}

/** AWS/geo region → Bedrock inference-profile prefix (us-east-1 → `us`). */
export function geoPrefix(region?: string | null): string | null {
  if (!region) return null;
  const r = region.toLowerCase();
  if (r === "global") return null;
  if (r.startsWith("us")) return "us";
  if (r.startsWith("eu")) return "eu";
  if (r.startsWith("ap")) return "apac";
  return null;
}

/**
 * Shared transport defaults. Every provider extends this; the "standard"
 * (single-base-URL) providers reuse its `resolveEndpoint` verbatim, while
 * deployment hosts (azure/bedrock/vertex) override it.
 */
export abstract class BaseProvider implements ProviderAdapter {
  abstract readonly id: string;
  abstract readonly defaultBaseUrl: string;
  readonly authStyle: AuthStyle = "bearer";

  envKey(): string | undefined {
    return undefined;
  }
  envOptions(): ProviderOptions | undefined {
    return undefined;
  }
  /** Env base-URL override for the standard endpoint path (host-specific). */
  protected envBaseUrl(): string | undefined {
    return undefined;
  }
  inferFromModel(_model: string): boolean {
    return false;
  }

  upstreamModelId(
    model: string,
    opts: { regionPrefix?: boolean; region?: string | null },
  ): string {
    if (opts.regionPrefix) {
      const geo = geoPrefix(opts.region);
      if (geo) return `${geo}.${model}`;
    }
    return model;
  }

  adjustBody(
    body: Record<string, unknown>,
    _family: ModelFamily,
  ): Record<string, unknown> {
    return body;
  }
  wrapStream(
    body: ReadableStream<Uint8Array>,
    _family: ModelFamily,
  ): ReadableStream<Uint8Array> {
    return body;
  }

  /** Auth headers for the standard path (query-style hosts return non-secret only). */
  protected authHeaders(token: string): Record<string, string> {
    return { Authorization: `Bearer ${token}` };
  }
  /** Path (relative to base URL) for a capability. Deployment hosts don't use this. */
  protected endpointFor(_capability: Capability, _streaming: boolean): string {
    throw new Error(`${this.id}: use resolveEndpoint`);
  }

  /** Effective base URL: BYOK cred > env override > provider default. */
  protected resolveBaseUrl(byokBaseUrl?: string | null): string {
    const byok = byokBaseUrl?.trim();
    if (byok) return stripTrailingSlash(byok);
    const override = this.envBaseUrl()?.trim();
    if (override) return stripTrailingSlash(override);
    return stripTrailingSlash(this.defaultBaseUrl);
  }

  resolveEndpoint(ctx: EndpointCtx): {
    url: string;
    headers: Record<string, string>;
  } {
    const base = this.resolveBaseUrl(ctx.byokBaseUrl);
    let url =
      base +
      this.endpointFor(ctx.capability, ctx.stream).replace("{model}", ctx.model);
    const headers: Record<string, string> = {
      "content-type": "application/json",
      ...this.authHeaders(ctx.token),
    };
    if (this.authStyle === "query") {
      const sep = url.includes("?") ? "&" : "?";
      url += `${sep}key=${encodeURIComponent(ctx.token)}`;
      if (ctx.stream) url += "&alt=sse";
    }
    return { url, headers };
  }
}
