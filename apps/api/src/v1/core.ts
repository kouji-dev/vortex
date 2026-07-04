import { randomUUID } from "node:crypto";
import { and, eq } from "drizzle-orm";
import {
  withOrg,
  withBypass,
  apps,
  models,
  providerCredentials,
  usageRecords,
} from "@vortex/db";
import {
  env,
  getProvider,
  resolveEndpoint,
  listEnabledProviders,
  decryptForOrg,
  type Capability,
  type ProviderOptions,
} from "@vortex/core";
import type { CanonicalChatRequest, Usage } from "@vortex/shared";
import {
  assertWithinBudget,
  commitSpend,
} from "../features/governance/budget.service.js";
import type { GatewayCtx } from "./gateway.auth.js";
import { getAdapter, type OpenAIChatCompletion } from "./providers/index.js";
import {
  costMicro,
  estimatePromptTokens,
  lookupPrice,
  type Price,
} from "./cost.js";

// ── target resolution ────────────────────────────────────────

export type Target = {
  provider: string;
  model: string;
  token: string;
  priceOverride?: { inputPer1k?: number; outputPer1k?: number } | null;
  credentialId?: string | null;
  appId: string | null;
  options?: ProviderOptions | null;
};

function envKeyFor(providerId: string): string | undefined {
  switch (providerId) {
    case "openai":
      return env.OPENAI_API_KEY;
    case "anthropic":
      return env.ANTHROPIC_API_KEY;
    case "google":
      return env.GOOGLE_API_KEY;
    case "azure":
      return env.AZURE_OPENAI_API_KEY;
    case "bedrock":
      return env.AWS_BEDROCK_API_KEY;
    case "vertex":
      return env.GOOGLE_VERTEX_API_KEY;
    default:
      return undefined;
  }
}

/** Deployment options from env (single-tenant defaults) for a provider. */
function envOptionsFor(providerId: string): ProviderOptions | undefined {
  switch (providerId) {
    case "azure":
      return {
        azureResource: env.AZURE_OPENAI_RESOURCE,
        azureApiVersion: env.AZURE_OPENAI_API_VERSION,
      };
    case "bedrock":
      return { region: env.AWS_BEDROCK_REGION };
    case "vertex":
      return {
        project: env.GOOGLE_VERTEX_PROJECT,
        region: env.GOOGLE_VERTEX_REGION,
      };
    default:
      return undefined;
  }
}

/** Resolve `{provider, model}` from a request model string. */
async function resolveModel(
  modelStr: string,
): Promise<{ provider: string; model: string } | null> {
  const slash = modelStr.indexOf("/");
  if (slash > 0) {
    const provider = modelStr.slice(0, slash);
    if (getProvider(provider))
      return { provider, model: modelStr.slice(slash + 1) };
  }
  const enabled = listEnabledProviders().map((p) => p.id);
  if (enabled.length === 0) return null;
  const rows = await withBypass((tx) =>
    tx.select().from(models).where(eq(models.modelName, modelStr)),
  );
  const hit = rows.find((r) => enabled.includes(r.provider));
  if (hit) return { provider: hit.provider, model: modelStr };
  return { provider: enabled[0]!, model: modelStr };
}

/** Resolve a credential (app→org) or fall back to the env provider key. */
async function resolveTarget(
  ctx: GatewayCtx,
  modelStr: string,
): Promise<Target | null> {
  const resolved = await resolveModel(modelStr);
  if (!resolved) return null;
  const { provider, model } = resolved;

  return withOrg(ctx.orgId, async (tx) => {
    let appId: string | null = null;
    if (ctx.actingAppSlug) {
      const [a] = await tx
        .select()
        .from(apps)
        .where(eq(apps.name, ctx.actingAppSlug))
        .limit(1);
      appId = a?.id ?? null;
    }

    let cred:
      | typeof providerCredentials.$inferSelect
      | undefined;
    if (appId) {
      [cred] = await tx
        .select()
        .from(providerCredentials)
        .where(
          and(
            eq(providerCredentials.provider, provider),
            eq(providerCredentials.enabled, true),
            eq(providerCredentials.scopeType, "app"),
            eq(providerCredentials.scopeId, appId),
          ),
        )
        .limit(1);
    }
    if (!cred) {
      [cred] = await tx
        .select()
        .from(providerCredentials)
        .where(
          and(
            eq(providerCredentials.provider, provider),
            eq(providerCredentials.enabled, true),
            eq(providerCredentials.scopeType, "org"),
          ),
        )
        .limit(1);
    }

    if (cred) {
      return {
        provider,
        model,
        token: decryptForOrg(ctx.orgId, cred.encryptedKey),
        priceOverride: cred.priceOverride,
        credentialId: cred.id,
        appId,
        options: {
          ...(cred.options ?? {}),
          ...(cred.region ? { region: cred.region } : {}),
        } as ProviderOptions,
      };
    }

    const envKey = envKeyFor(provider);
    if (!envKey) return null;
    return {
      provider,
      model,
      token: envKey,
      appId,
      options: envOptionsFor(provider),
    };
  });
}

// ── upstream request builder ─────────────────────────────────

function buildUpstream(opts: {
  provider: string;
  model: string;
  capability: Capability;
  streaming: boolean;
  token: string;
  options?: ProviderOptions | null;
}): { url: string; headers: Record<string, string> } {
  return resolveEndpoint(opts.provider, {
    token: opts.token,
    model: opts.model,
    capability: opts.capability,
    stream: opts.streaming,
    options: opts.options ?? null,
  });
}

// ── usage finalization (cost + spend + record) ───────────────

async function finalize(
  ctx: GatewayCtx,
  target: Target,
  usage: Usage,
  latencyMs: number,
  status: "success" | "error",
): Promise<void> {
  let price: Price | null = null;
  try {
    price = await lookupPrice(target.provider, target.model, target.priceOverride);
  } catch {
    /* price lookup best-effort */
  }
  const cm = costMicro(usage, price);
  try {
    await commitSpend({
      orgId: ctx.orgId,
      memberId: ctx.memberId,
      actualMicro: cm,
    });
  } catch {
    /* spend commit best-effort — usage row is still recorded */
  }
  try {
    await withOrg(ctx.orgId, (tx) =>
      tx.insert(usageRecords).values({
        requestId: randomUUID(),
        orgId: ctx.orgId,
        apiKeyId: ctx.apiKeyId,
        memberId: ctx.memberId,
        appId: target.appId,
        teamId: ctx.teamId,
        actingUserId: ctx.actingUserId,
        provider: target.provider,
        model: target.model,
        promptTokens: usage.promptTokens,
        completionTokens: usage.completionTokens,
        totalTokens: usage.totalTokens,
        costMicro: cm,
        status,
        latencyMs,
      }),
    );
  } catch {
    /* usage insert best-effort */
  }
}

// ── the single core chat handler ─────────────────────────────

export type ChatResult =
  | { kind: "json"; openai: OpenAIChatCompletion }
  | { kind: "stream"; stream: ReadableStream<Uint8Array>; model: string }
  | { kind: "error"; status: number; body: unknown };

function errBody(message: string, type: string, code?: string) {
  return { error: { message, type, param: null, code: code ?? null } };
}

/**
 * Canonical chat handler (hub). Resolves provider/model + credential, enforces
 * budget, calls upstream, meters usage/cost, commits spend, records usage.
 */
export async function handleChat(
  ctx: GatewayCtx,
  canonical: CanonicalChatRequest,
): Promise<ChatResult> {
  const target = await resolveTarget(ctx, canonical.model);
  if (!target) {
    return {
      kind: "error",
      status: 400,
      body: errBody(
        `No provider/credential available for model '${canonical.model}'.`,
        "invalid_request_error",
        "model_not_found",
      ),
    };
  }

  const adapter = getAdapter(target.provider);
  const streaming = canonical.stream === true;

  // Budget pre-check: estimate = prompt tokens (in) + max_tokens (out).
  const price = await lookupPrice(
    target.provider,
    target.model,
    target.priceOverride,
  );
  const estMicro = costMicro(
    {
      promptTokens: estimatePromptTokens(canonical),
      completionTokens: canonical.maxTokens ?? 0,
      totalTokens: 0,
    },
    price,
  );
  await assertWithinBudget({
    orgId: ctx.orgId,
    memberId: ctx.memberId,
    estimateMicro: estMicro,
  });

  const body = adapter.toProviderBody(canonical, target.model, streaming);
  const { url, headers } = buildUpstream({
    provider: target.provider,
    model: target.model,
    capability: adapter.chatCapability,
    streaming,
    token: target.token,
    options: target.options,
  });

  const started = Date.now();
  let resp: Response;
  try {
    resp = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
  } catch (e) {
    await finalize(
      ctx,
      target,
      { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      Date.now() - started,
      "error",
    );
    return {
      kind: "error",
      status: 502,
      body: errBody(
        `Upstream request failed: ${(e as Error).message}`,
        "api_error",
      ),
    };
  }

  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    await finalize(
      ctx,
      target,
      { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      Date.now() - started,
      "error",
    );
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = errBody(text || "Upstream error", "api_error");
    }
    return { kind: "error", status: resp.status, body: parsed };
  }

  if (streaming) {
    if (!resp.body) {
      return {
        kind: "error",
        status: 502,
        body: errBody("Upstream returned no stream body.", "api_error"),
      };
    }
    const { stream, usage } = adapter.streamTransform(resp.body, target.model);
    // Finalize once the stream is fully consumed downstream.
    void usage.then((u) => finalize(ctx, target, u, Date.now() - started, "success"));
    return { kind: "stream", stream, model: target.model };
  }

  const json = await resp.json().catch(() => ({}));
  const { openai, usage } = adapter.fromProviderResponse(json, target.model);
  await finalize(ctx, target, usage, Date.now() - started, "success");
  return { kind: "json", openai };
}

// ── embeddings (direct proxy + metering) ─────────────────────

export async function handleEmbeddings(
  ctx: GatewayCtx,
  req: { model: string; input: unknown } & Record<string, unknown>,
): Promise<ChatResult> {
  const target = await resolveTarget(ctx, req.model);
  if (!target) {
    return {
      kind: "error",
      status: 400,
      body: errBody(
        `No provider/credential available for model '${req.model}'.`,
        "invalid_request_error",
        "model_not_found",
      ),
    };
  }
  const { url, headers } = buildUpstream({
    provider: target.provider,
    model: target.model,
    capability: "embeddings",
    streaming: false,
    token: target.token,
    options: target.options,
  });
  const started = Date.now();
  const resp = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify({ ...req, model: target.model }),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    await finalize(
      ctx,
      target,
      { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      Date.now() - started,
      "error",
    );
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = errBody(text || "Upstream error", "api_error");
    }
    return { kind: "error", status: resp.status, body: parsed };
  }
  const json = (await resp.json().catch(() => ({}))) as any;
  const usage: Usage = {
    promptTokens: json.usage?.prompt_tokens ?? 0,
    completionTokens: 0,
    totalTokens: json.usage?.total_tokens ?? json.usage?.prompt_tokens ?? 0,
  };
  await finalize(ctx, target, usage, Date.now() - started, "success");
  return { kind: "json", openai: json };
}
