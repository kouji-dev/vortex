import { env } from "../../config/env.js";
import { BaseProvider, stripTrailingSlash } from "./base.js";
import type { AuthStyle, EndpointCtx, ProviderOptions } from "./types.js";

// Azure OpenAI (deployment-scoped endpoint built from resource + deployment).
export class AzureProvider extends BaseProvider {
  readonly id = "azure";
  readonly defaultBaseUrl = "https://RESOURCE.openai.azure.com";
  override readonly authStyle: AuthStyle = "x-api-key";

  override envKey() {
    return env.AZURE_OPENAI_API_KEY;
  }
  override envOptions(): ProviderOptions {
    return {
      azureResource: env.AZURE_OPENAI_RESOURCE,
      azureApiVersion: env.AZURE_OPENAI_API_VERSION,
    };
  }

  override resolveEndpoint(ctx: EndpointCtx) {
    const o = ctx.options ?? {};
    const byok = ctx.byokBaseUrl?.trim();
    const resource = o.azureResource ?? env.AZURE_OPENAI_RESOURCE;
    if (!resource) throw new Error("azure: missing resource");
    const apiVersion =
      o.azureApiVersion ?? env.AZURE_OPENAI_API_VERSION ?? "2024-10-21";
    const deployment = o.deployment ?? ctx.model;
    const base = byok || `https://${resource}.openai.azure.com`;
    const kind =
      ctx.capability === "embeddings" ? "embeddings" : "chat/completions";
    return {
      url: `${stripTrailingSlash(base)}/openai/deployments/${deployment}/${kind}?api-version=${apiVersion}`,
      headers: { "content-type": "application/json", "api-key": ctx.token },
    };
  }
}

export const azureProvider = new AzureProvider();
