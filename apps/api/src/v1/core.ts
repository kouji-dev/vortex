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
  getAdapter,
  getProviderAdapter,
  inferProviderId,
  listEnabledProviders,
  decryptForOrg,
  PLATFORM_SCOPE,
  hostMeta,
  type Capability,
  type ProviderAdapter,
  type ProviderOptions,
  type ModelFamily,
  type SupportedFeatures,
  type OpenAIChatCompletion,
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
import {
  costMicro,
  estimatePromptTokens,
  estTokensFromChars,
  lookupPrice,
  catalogRows,
  type Price,
} from "./cost.js";

// ── target resolution ────────────────────────────────────────

export type Target = {
  /** Host id (openai/anthropic/azure/bedrock/vertex/groq…) = credential.provider. */
  provider: string;
  /** Logical model id (for pricing + usage records). */
  model: string;
  /** Wire envelope — picks the adapter + endpoint path on multi-family hosts. */
  family: ModelFamily;
  /** Provider-specific id sent upstream (pre region-prefix). */
  upstreamModelId: string;
  /** Whether the host region-prefixes the model id (Bedrock inference profiles). */
  regionPrefix?: boolean;
  /** Per-host cap; reject when the request asks for more. */
  maxOutput?: number | null;
  /** Per-host×model capability gate. */
  supportedFeatures?: SupportedFeatures | null;
  token: string;
  priceOverride?: { inputPer1k?: number; outputPer1k?: number } | null;
  credentialId?: string | null;
  appId: string | null;
  options?: ProviderOptions | null;
  /** Served from the Vortex-managed pool → deduct credits + markup. */
  managed?: boolean;
  markupBps?: number;
};

/** One resolved place a logical model can be served (host + envelope + id). */
type ModelCandidate = {
  host: string;
  family: ModelFamily;
  model: string; // logical
  upstreamModelId: string;
  regionPrefix: boolean;
  maxOutput: number | null;
  supportedFeatures: SupportedFeatures | null;
};

/** Default wire family for a host (drives inference + unprefixed pins). */
function hostDefaultFamily(host: string): ModelFamily {
  return hostMeta(host)?.defaultFamily ?? "openai";
}

/**
 * Ordered (host, family, upstreamModelId) candidates for a request model string.
 * A `{host}/{model}` prefix pins the host; a bare model expands to every enabled
 * host that serves it (so the credential the org holds decides which is used).
 */
async function resolveCandidates(modelStr: string): Promise<ModelCandidate[]> {
  const rows = await catalogRows();
  const toCand = (
    r: (typeof rows)[number],
    logical: string,
  ): ModelCandidate => ({
    host: r.provider,
    family: (r.family ?? hostDefaultFamily(r.provider)) as ModelFamily,
    model: logical,
    upstreamModelId: r.upstreamModelId ?? logical,
    regionPrefix: Boolean(
      (r.config as { regionPrefix?: boolean } | null)?.regionPrefix,
    ),
    maxOutput: r.maxOutput ?? null,
    supportedFeatures: r.supportedFeatures ?? null,
  });
  const bare = (host: string, logical: string): ModelCandidate => ({
    host,
    family: hostDefaultFamily(host),
    model: logical,
    upstreamModelId: logical,
    regionPrefix: false,
    maxOutput: null,
    supportedFeatures: null,
  });

  // Explicit `{host}/{model}` pin.
  const slash = modelStr.indexOf("/");
  if (slash > 0) {
    const host = modelStr.slice(0, slash);
    const sub = modelStr.slice(slash + 1);
    if (getProviderAdapter(host)) {
      const row = rows.find((r) => r.provider === host && r.modelName === sub);
      return [row ? toCand(row, sub) : bare(host, sub)];
    }
  }

  const enabled = new Set(listEnabledProviders().map((p) => p.id));
  if (enabled.size === 0) return [];
  // Bare model → every enabled host that serves it (credential picks the winner).
  const matches = rows.filter(
    (r) => r.modelName === modelStr && enabled.has(r.provider),
  );
  if (matches.length) return matches.map((r) => toCand(r, modelStr));
  // Unknown model → infer family-host, else first enabled host.
  const inferred = inferProviderId(modelStr);
  if (inferred && enabled.has(inferred)) return [bare(inferred, modelStr)];
  const first = listEnabledProviders()[0];
  return first ? [bare(first.id, modelStr)] : [];
}

/** Merge a resolved candidate + credential source into a Target. */
function mkTarget(
  cand: ModelCandidate,
  base: Omit<Target, "provider" | "model" | "family" | "upstreamModelId" | "regionPrefix" | "maxOutput" | "supportedFeatures">,
): Target {
  return {
    provider: cand.host,
    model: cand.model,
    family: cand.family,
    upstreamModelId: cand.upstreamModelId,
    regionPrefix: cand.regionPrefix,
    maxOutput: cand.maxOutput,
    supportedFeatures: cand.supportedFeatures,
    ...base,
  };
}

/**
 * Resolve the upstream target: pick the first candidate host with a usable
 * credential (BYOK app→org, then managed pool, then env key). Model resolution
 * and credential selection are joined so the org's credential decides the host.
 */
async function resolveTarget(
  ctx: GatewayCtx,
  modelStr: string,
): Promise<Target | null> {
  const candidates = await resolveCandidates(modelStr);
  if (!candidates.length) return null;

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

    // 1) BYOK credential (app→org) — first candidate host that has one.
    for (const cand of candidates) {
      let cred: typeof providerCredentials.$inferSelect | undefined;
      if (appId) {
        [cred] = await tx
          .select()
          .from(providerCredentials)
          .where(
            and(
              eq(providerCredentials.provider, cand.host),
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
              eq(providerCredentials.provider, cand.host),
              eq(providerCredentials.enabled, true),
              eq(providerCredentials.scopeType, "org"),
            ),
          )
          .limit(1);
      }
      if (cred) {
        return mkTarget(cand, {
          token: decryptForOrg(ctx.orgId, cred.encryptedKey),
          priceOverride: cred.priceOverride,
          credentialId: cred.id,
          appId,
          options: {
            ...(cred.options ?? {}),
            ...(cred.region ? { region: cred.region } : {}),
          } as ProviderOptions,
        });
      }
    }

    // 2) Managed pool (managed/hybrid orgs). Self-hosted skips the billing-plane
    // query entirely and falls through to the env key (hot-path saving).
    if (env.DEPLOYMENT_MODE === "managed") {
      const [org] = await tx
        .select({ keyMode: organizations.keyMode, markupBps: organizations.markupBps })
        .from(organizations)
        .where(eq(organizations.id, ctx.orgId))
        .limit(1);
      if (org && org.keyMode !== "byok") {
        for (const cand of candidates) {
          const [mk] = await tx
            .select()
            .from(managedProviderKeys)
            .where(
              and(
                eq(managedProviderKeys.provider, cand.host),
                eq(managedProviderKeys.enabled, true),
              ),
            )
            .limit(1);
          if (mk) {
            return mkTarget(cand, {
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
            });
          }
        }
      }
    }

    // 3) Env key — first candidate host with a configured key.
    for (const cand of candidates) {
      const provider = getProviderAdapter(cand.host);
      const envKey = provider?.envKey();
      if (envKey)
        return mkTarget(cand, {
          token: envKey,
          appId,
          options: provider?.envOptions(),
        });
    }
    return null;
  });
}

/** Provider (transport) adapter for a resolved target. */
function providerFor(target: Target): ProviderAdapter {
  const p = getProviderAdapter(target.provider);
  if (!p) throw new Error(`unknown provider '${target.provider}'`);
  return p;
}

/** Final upstream model id — region-prefixed when the host requires it. */
function upstreamId(target: Target): string {
  return providerFor(target).upstreamModelId(target.upstreamModelId, {
    regionPrefix: target.regionPrefix,
    region: target.options?.region,
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

/** The error variant shared by ChatResult + NativeResult (preflight output). */
type GatewayError = Extract<ChatResult, { kind: "error" }>;

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
function rateLimitError(e: RateLimitExceededError): GatewayError {
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
 * Shared governance pre-flight for both the canonical and native-passthrough
 * paths: price → budget (402) → managed credit (402) → rate limit (429) →
 * concurrency (429). Returns an acquired slot + rate headers, or a ready error.
 * `assertWithinBudget` throws BudgetExceededError (caught by the router as 402).
 */
type Preflight =
  | { ok: false; result: GatewayError }
  | { ok: true; headers: Record<string, string>; slot: ConcurrencySlot; estTokens: number };

async function preflight(
  ctx: GatewayCtx,
  target: Target,
  est: { promptTokens: number; maxTokens: number },
): Promise<Preflight> {
  const price = await lookupPrice(
    target.provider,
    target.model,
    target.priceOverride,
  );
  const estTokens = est.promptTokens + est.maxTokens;
  const estMicro = costMicro(
    { promptTokens: est.promptTokens, completionTokens: est.maxTokens, totalTokens: 0 },
    price,
  );

  if (target.managed && !price) {
    return {
      ok: false,
      result: {
        kind: "error",
        status: 400,
        body: errBody(
          `Model '${target.model}' has no managed-pool price.`,
          "invalid_request_error",
          "model_not_priced",
        ),
      },
    };
  }

  await assertWithinBudget({
    orgId: ctx.orgId,
    teamId: ctx.teamId,
    estimateMicro: estMicro,
  });

  if (target.managed) {
    const estCharge = Math.round(estMicro * (1 + (target.markupBps ?? 0) / 10_000));
    try {
      await assertCredit(ctx.orgId, estCharge);
    } catch (e) {
      if (e instanceof CreditExhaustedError)
        return {
          ok: false,
          result: {
            kind: "error",
            status: 402,
            body: errBody("Managed credits exhausted.", "insufficient_quota", "credits_exhausted"),
          },
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
    if (e instanceof RateLimitExceededError)
      return { ok: false, result: rateLimitError(e) };
    throw e;
  }
  const headers = rateHeaders(rlHeaders);

  const slot = await acquireConcurrency(ctx.orgId, ctx.apiKeyId);
  if (!slot.ok) {
    return {
      ok: false,
      result: {
        kind: "error",
        status: 429,
        body: errBody("Too many concurrent requests.", "rate_limit_exceeded", "concurrency_limit"),
        headers: { ...headers, "retry-after": "1" },
      },
    };
  }
  return { ok: true, headers, slot, estTokens };
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

  const adapter = getAdapter(target.family);
  const provider = providerFor(target);
  const streaming = canonical.stream === true;

  // Capability gate: reject a request that asks for a feature this host×model
  // does not serve (e.g. tools on a text-only host) before spending anything.
  if (
    canonical.tools?.length &&
    target.supportedFeatures &&
    target.supportedFeatures.tools === false
  ) {
    return {
      kind: "error",
      status: 400,
      body: errBody(
        `Model '${target.model}' on host '${target.provider}' does not support tools.`,
        "invalid_request_error",
        "feature_unsupported",
      ),
    };
  }

  const promptEst = estimatePromptTokens(canonical);
  const pf = await preflight(ctx, target, {
    promptTokens: promptEst,
    maxTokens: canonical.maxTokens ?? 0,
  });
  if (!pf.ok) return pf.result;
  const { headers, slot, estTokens } = pf;

  const wireModel = upstreamId(target);
  const body = provider.adjustBody(
    adapter.toProviderBody(canonical, wireModel, streaming),
    target.family,
  );
  const { url, headers: upstreamHeaders } = provider.resolveEndpoint({
    token: target.token,
    model: wireModel,
    family: target.family,
    capability: adapter.chatCapability,
    stream: streaming,
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
    const { stream, usage } = adapter.streamTransform(
      provider.wrapStream(resp.body, target.family),
      target.model,
    );
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
  // v1 embeddings: OpenAI-wire hosts only (Google `embedContent` shape differs).
  if (target.family !== "openai") {
    return {
      kind: "error",
      status: 400,
      body: errBody(
        `Embeddings are not supported for host '${target.provider}' (family '${target.family}').`,
        "invalid_request_error",
        "embeddings_unsupported",
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

  const wireModel = upstreamId(target);
  const { url, headers } = providerFor(target).resolveEndpoint({
    token: target.token,
    model: wireModel,
    family: target.family,
    capability: "embeddings",
    stream: false,
    options: target.options,
  });
  const started = Date.now();
  const resp = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify({ ...req, model: wireModel }),
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

// ── native passthrough (faithful same-family forwarding) ─────
// Forward a client's OWN request format straight to the matching-family host,
// unchanged (tools / images / thinking / caching intact) — only the model id and
// host-specific tweaks are applied. Response/stream are returned verbatim; usage
// is sniffed (read-only) for metering. Cross-format routing is deferred.

export type NativeResult =
  | { kind: "json"; json: unknown; headers?: Record<string, string> }
  | { kind: "stream"; stream: ReadableStream<Uint8Array>; headers?: Record<string, string> }
  | { kind: "error"; status: number; body: unknown; headers?: Record<string, string> };

export interface NativeRequest {
  model: string;
  rawBody: Record<string, unknown>;
  stream: boolean;
  /** The wire family of the inbound surface (messages→anthropic, responses/chat→openai). */
  inboundFamily: ModelFamily;
  /** Upstream capability/endpoint to hit (messages | responses | chat). */
  capability: Capability;
  promptChars: number;
  maxTokens: number;
  hasTools: boolean;
  /** Provider-native headers to forward upstream (anthropic-version/-beta, openai-beta). */
  extraHeaders?: Record<string, string>;
}

export async function handleNative(
  ctx: GatewayCtx,
  n: NativeRequest,
): Promise<NativeResult> {
  const target = await resolveTarget(ctx, n.model);
  if (!target)
    return {
      kind: "error",
      status: 400,
      body: errBody(
        `No provider/credential available for model '${n.model}'.`,
        "invalid_request_error",
        "model_not_found",
      ),
    };

  // Native forwards the client's own format → the target must serve that family.
  // Cross-format (e.g. Claude Code → a GPT model) is deferred to smart routing.
  if (target.family !== n.inboundFamily)
    return {
      kind: "error",
      status: 400,
      body: errBody(
        `Model '${target.model}' is served in the '${target.family}' format; this endpoint speaks '${n.inboundFamily}'. Cross-format routing is not enabled.`,
        "invalid_request_error",
        "cross_format_unsupported",
      ),
    };

  if (n.hasTools && target.supportedFeatures?.tools === false)
    return {
      kind: "error",
      status: 400,
      body: errBody(
        `Model '${target.model}' on host '${target.provider}' does not support tools.`,
        "invalid_request_error",
        "feature_unsupported",
      ),
    };

  const pf = await preflight(ctx, target, {
    promptTokens: estTokensFromChars(n.promptChars),
    maxTokens: n.maxTokens,
  });
  if (!pf.ok) return pf.result;
  const { headers, slot, estTokens } = pf;

  const provider = providerFor(target);
  const adapter = getAdapter(target.family);

  const wireModel = upstreamId(target);
  let body: Record<string, unknown> = { ...n.rawBody, model: wireModel };
  // Meter OpenAI-family Chat streaming via the trailing usage chunk.
  if (
    n.stream &&
    target.family === "openai" &&
    n.capability === "chat" &&
    body.stream_options == null
  ) {
    body.stream_options = { include_usage: true };
  }
  body = provider.adjustBody(body, target.family);

  const { url, headers: upstreamHeaders } = provider.resolveEndpoint({
    token: target.token,
    model: wireModel,
    family: target.family,
    capability: n.capability,
    stream: n.stream,
    options: target.options,
  });
  const merged = { ...upstreamHeaders, ...(n.extraHeaders ?? {}) };

  const started = Date.now();
  let resp: Response;
  try {
    resp = await fetch(url, {
      method: "POST",
      headers: merged,
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
      body: errBody(`Upstream request failed: ${(e as Error).message}`, "api_error"),
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

  if (n.stream) {
    if (!resp.body) {
      await slot.release();
      return {
        kind: "error",
        status: 502,
        body: errBody("Upstream returned no stream body.", "api_error"),
        headers,
      };
    }
    // Bedrock event-stream → Anthropic SSE; every other host is byte-identical.
    // tee: one branch to the client verbatim, one to the read-only usage sniffer.
    const client = provider.wrapStream(resp.body, target.family);
    const [toClient, toMeter] = client.tee();
    const usage = adapter.sniffStreamUsage(toMeter, n.capability);
    void usage.then((u) =>
      finalize(ctx, target, u, Date.now() - started, "success", { slot, estTokens }),
    );
    return { kind: "stream", stream: toClient, headers };
  }

  const json = await resp.json().catch(() => ({}));
  const usage = adapter.parseUsage(json, n.capability);
  await finalize(ctx, target, usage, Date.now() - started, "success", {
    slot,
    estTokens,
  });
  return { kind: "json", json, headers };
}

// Native usage extraction (streamed + non-streamed) now lives on the family
// adapter (sniffStreamUsage / parseUsage) — see ./providers/*.
