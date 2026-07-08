import { randomUUID } from "node:crypto";
import { and, eq } from "drizzle-orm";
import {
  withOrg,
  apps,
  organizations,
  providerCredentials,
  managedProviderKeys,
  usageRecords,
} from "@vortex/db";
import {
  env,
  getProvider,
  resolveEndpoint,
  listEnabledProviders,
  decryptForOrg,
  PLATFORM_SCOPE,
  type Capability,
  type ProviderOptions,
} from "@vortex/core";
import type { CanonicalChatRequest, Usage } from "@vortex/shared";
import {
  assertWithinBudget,
  commitSpend,
} from "../features/governance/budget.service.js";
import {
  checkRateLimits,
  acquireConcurrency,
  commitTokenDelta,
  RateLimitExceededError,
  type LimitHeaders,
  type ConcurrencySlot,
} from "../features/governance/rate-limit.service.js";
import {
  assertCredit,
  deductCredit,
  CreditExhaustedError,
} from "../features/billing/credits.service.js";
import type { GatewayCtx } from "./gateway.auth.js";
import { getAdapter, type OpenAIChatCompletion } from "./providers/index.js";
import {
  costMicro,
  estimatePromptTokens,
  lookupPrice,
  catalogRows,
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
  /** Served from the Vortex-managed pool → deduct credits + markup. */
  managed?: boolean;
  markupBps?: number;
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

/**
 * Infer the provider from a model-name family so unprefixed models route
 * correctly (e.g. Claude Code sends `claude-*` to /v1/messages with no prefix).
 */
function inferProvider(model: string): string | null {
  const m = model.toLowerCase();
  if (m.startsWith("claude")) return "anthropic";
  if (m.startsWith("gemini")) return "google";
  if (
    m.startsWith("gpt") ||
    m.startsWith("chatgpt") ||
    m.startsWith("text-embedding") ||
    /^o[1-9]/.test(m) // o1 / o3 / o4 …
  )
    return "openai";
  return null;
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
  // 1) exact catalog match (in-memory, cached), 2) model-family inference,
  // 3) first enabled.
  const rows = (await catalogRows()).filter((r) => r.modelName === modelStr);
  const hit = rows.find((r) => enabled.includes(r.provider));
  if (hit) return { provider: hit.provider, model: modelStr };
  const inferred = inferProvider(modelStr);
  if (inferred && enabled.includes(inferred))
    return { provider: inferred, model: modelStr };
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

    // No BYOK credential → managed pool for managed/hybrid orgs. Self-hosted has
    // no billing plane, so skip the org keyMode/markup fetch entirely there and
    // fall straight through to the env key (saves a query on the hot path).
    if (env.DEPLOYMENT_MODE === "managed") {
      const [org] = await tx
        .select({ keyMode: organizations.keyMode, markupBps: organizations.markupBps })
        .from(organizations)
        .where(eq(organizations.id, ctx.orgId))
        .limit(1);
      if (org && org.keyMode !== "byok") {
        const [mk] = await tx
          .select()
          .from(managedProviderKeys)
          .where(
            and(
              eq(managedProviderKeys.provider, provider),
              eq(managedProviderKeys.enabled, true),
            ),
          )
          .limit(1);
        if (mk) {
          return {
            provider,
            model,
            token: decryptForOrg(PLATFORM_SCOPE, mk.encryptedKey),
            priceOverride: mk.priceOverride,
            credentialId: mk.id,
            appId,
            options: {
              ...(mk.options ?? {}),
              ...(mk.region ? { region: mk.region } : {}),
            } as ProviderOptions,
            managed: true,
            markupBps: org.markupBps,
          };
        }
      }
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
  extra?: { slot?: ConcurrencySlot; estTokens?: number },
): Promise<void> {
  // Release the in-flight slot + reconcile the TPM estimate first (fast, local).
  if (extra?.slot) await extra.slot.release();
  if (extra?.estTokens != null) {
    await commitTokenDelta({
      orgId: ctx.orgId,
      apiKeyId: ctx.apiKeyId,
      estTokens: extra.estTokens,
      actualTokens: usage.totalTokens,
    });
  }
  // Price comes from the cached catalog (in-memory); pool is memoized per
  // request — both cheap, so no threading needed.
  let price: Price | null = null;
  try {
    price = await lookupPrice(target.provider, target.model, target.priceOverride);
  } catch {
    /* price lookup best-effort */
  }
  const cm = costMicro(usage, price);
  const rid = randomUUID();
  try {
    await commitSpend({
      orgId: ctx.orgId,
      teamId: ctx.teamId,
      actualMicro: cm,
    });
  } catch {
    /* spend commit best-effort — usage row is still recorded */
  }
  // Managed pool → bill the org's credit wallet (cost + markup).
  if (target.managed) {
    try {
      await deductCredit({
        orgId: ctx.orgId,
        costMicro: cm,
        markupBps: target.markupBps ?? 0,
        requestId: rid,
      });
    } catch {
      /* credit deduction best-effort */
    }
  }
  try {
    await withOrg(ctx.orgId, (tx) =>
      tx.insert(usageRecords).values({
        requestId: rid,
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
  | { kind: "json"; openai: OpenAIChatCompletion; headers?: Record<string, string> }
  | {
      kind: "stream";
      stream: ReadableStream<Uint8Array>;
      model: string;
      headers?: Record<string, string>;
    }
  | { kind: "error"; status: number; body: unknown; headers?: Record<string, string> };

function errBody(message: string, type: string, code?: string) {
  return { error: { message, type, param: null, code: code ?? null } };
}

/** IETF + legacy rate-limit headers for the RPM bucket. */
function rateHeaders(h: LimitHeaders): Record<string, string> {
  if (!h.limit) return {};
  return {
    "ratelimit-limit": String(h.limit),
    "ratelimit-remaining": String(h.remaining),
    "ratelimit-reset": String(h.resetSec),
    "x-ratelimit-limit": String(h.limit),
    "x-ratelimit-remaining": String(h.remaining),
    "x-ratelimit-reset": String(h.resetSec),
  };
}

/** 429 result for a denied rate-limit bucket, with Retry-After. */
function rateLimitError(e: RateLimitExceededError): ChatResult {
  const retrySec = Math.max(1, Math.ceil(e.retryAfterMs / 1000));
  return {
    kind: "error",
    status: 429,
    body: errBody(
      `Rate limit exceeded (${e.dimension}). Retry in ${retrySec}s.`,
      "rate_limit_exceeded",
      "rate_limit_exceeded",
    ),
    headers: { "retry-after": String(retrySec) },
  };
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
  const promptEst = estimatePromptTokens(canonical);
  const estTokens = promptEst + (canonical.maxTokens ?? 0);
  const estMicro = costMicro(
    { promptTokens: promptEst, completionTokens: canonical.maxTokens ?? 0, totalTokens: 0 },
    price,
  );

  // Managed pool can only serve models it can price — an unpriced model would be
  // billed at 0 (free). Reject rather than serve unmetered managed usage.
  if (target.managed && !price) {
    return {
      kind: "error",
      status: 400,
      body: errBody(
        `Model '${target.model}' has no managed-pool price.`,
        "invalid_request_error",
        "model_not_priced",
      ),
    };
  }

  // Governance order: budget ($/team, 402) → rate limit (RPM/TPM, 429) →
  // concurrency (429) → proxy. Budget throws (caught upstream as 402).
  await assertWithinBudget({
    orgId: ctx.orgId,
    teamId: ctx.teamId,
    estimateMicro: estMicro,
  });

  // Managed pool → require credits to cover this request's estimated charge
  // (cost + markup), not just a non-empty wallet. 402 when short.
  if (target.managed) {
    const estCharge = Math.round(estMicro * (1 + (target.markupBps ?? 0) / 10_000));
    try {
      await assertCredit(ctx.orgId, estCharge);
    } catch (e) {
      if (e instanceof CreditExhaustedError)
        return {
          kind: "error",
          status: 402,
          body: errBody("Managed credits exhausted.", "insufficient_quota", "credits_exhausted"),
        };
      throw e;
    }
  }

  let rlHeaders: LimitHeaders;
  try {
    rlHeaders = await checkRateLimits({
      orgId: ctx.orgId,
      apiKeyId: ctx.apiKeyId,
      keyRpm: ctx.rateLimitRpm,
      estTokens,
    });
  } catch (e) {
    if (e instanceof RateLimitExceededError) return rateLimitError(e);
    throw e;
  }
  const headers = rateHeaders(rlHeaders);

  const slot = await acquireConcurrency(ctx.orgId, ctx.apiKeyId);
  if (!slot.ok) {
    return {
      kind: "error",
      status: 429,
      body: errBody("Too many concurrent requests.", "rate_limit_exceeded", "concurrency_limit"),
      headers: { ...headers, "retry-after": "1" },
    };
  }

  const body = adapter.toProviderBody(canonical, target.model, streaming);
  const { url, headers: upstreamHeaders } = buildUpstream({
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
      headers: upstreamHeaders,
      body: JSON.stringify(body),
    });
  } catch (e) {
    await finalize(
      ctx,
      target,
      { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      Date.now() - started,
      "error",
      { slot, estTokens },
    );
    return {
      kind: "error",
      status: 502,
      body: errBody(
        `Upstream request failed: ${(e as Error).message}`,
        "api_error",
      ),
      headers,
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
      { slot, estTokens },
    );
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = errBody(text || "Upstream error", "api_error");
    }
    return { kind: "error", status: resp.status, body: parsed, headers };
  }

  if (streaming) {
    if (!resp.body) {
      await slot.release();
      return {
        kind: "error",
        status: 502,
        body: errBody("Upstream returned no stream body.", "api_error"),
        headers,
      };
    }
    const { stream, usage } = adapter.streamTransform(resp.body, target.model);
    // Finalize (release slot + meter) once the stream is fully consumed.
    void usage.then((u) =>
      finalize(ctx, target, u, Date.now() - started, "success", {
        slot,
        estTokens,
      }),
    );
    return { kind: "stream", stream, model: target.model, headers };
  }

  const json = await resp.json().catch(() => ({}));
  const { openai, usage } = adapter.fromProviderResponse(json, target.model);
  await finalize(ctx, target, usage, Date.now() - started, "success", {
    slot,
    estTokens,
  });
  return { kind: "json", openai, headers };
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
  // Rate limit (RPM) + concurrency. TPM is metered post-response via the delta.
  let rlHeaders: LimitHeaders;
  try {
    rlHeaders = await checkRateLimits({
      orgId: ctx.orgId,
      apiKeyId: ctx.apiKeyId,
      keyRpm: ctx.rateLimitRpm,
      estTokens: 0,
    });
  } catch (e) {
    if (e instanceof RateLimitExceededError) return rateLimitError(e);
    throw e;
  }
  const rHeaders = rateHeaders(rlHeaders);
  const slot = await acquireConcurrency(ctx.orgId, ctx.apiKeyId);
  if (!slot.ok) {
    return {
      kind: "error",
      status: 429,
      body: errBody("Too many concurrent requests.", "rate_limit_exceeded", "concurrency_limit"),
      headers: { ...rHeaders, "retry-after": "1" },
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
      { slot, estTokens: 0 },
    );
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = errBody(text || "Upstream error", "api_error");
    }
    return { kind: "error", status: resp.status, body: parsed, headers: rHeaders };
  }
  const json = (await resp.json().catch(() => ({}))) as any;
  const usage: Usage = {
    promptTokens: json.usage?.prompt_tokens ?? 0,
    completionTokens: 0,
    totalTokens: json.usage?.total_tokens ?? json.usage?.prompt_tokens ?? 0,
  };
  await finalize(ctx, target, usage, Date.now() - started, "success", {
    slot,
    estTokens: 0,
  });
  return { kind: "json", openai: json, headers: rHeaders };
}
