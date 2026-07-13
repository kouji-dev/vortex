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
  reserveSpend,
  settleSpend,
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
  walletBalance,
  deductCredit,
  CreditExhaustedError,
} from "../features/billing/credits.service.js";
import { recordBillingFailure } from "../features/billing/billing-dlq.service.js";
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

type ResolveOutcome =
  | { ok: true; candidates: [Target, ...Target[]] }
  | { ok: false; reason: "model_not_found" | "no_credential" };

/** Default wire family for a host (drives inference + unprefixed pins). */
function hostDefaultFamily(host: string): ModelFamily {
  return hostMeta(host)?.defaultFamily ?? "openai";
}

/**
 * Ordered (host, family, upstreamModelId) candidates for a request model string.
 * A `{host}/{model}` prefix pins the host; a bare model expands to every enabled
 * host that serves it (so the credential the org holds decides which is used).
 * An unknown model that can't be catalog-matched or family-inferred resolves to
 * NO candidates → 400 model_not_found (never silently routed to an arbitrary host).
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
  // Unknown model → family-host inference only. No last-resort host: an
  // unmatched model must 400, not land on whichever provider is enabled first.
  const inferred = inferProviderId(modelStr);
  if (inferred && enabled.has(inferred)) return [bare(inferred, modelStr)];
  return [];
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
 * Resolve the upstream targets: the first candidate host with a usable
 * credential (BYOK app→org, then managed pool, then env key). For a BYOK host
 * EVERY enabled credential becomes a failover candidate (primary first), so a
 * 5xx on the first key can retry on the next one. Model resolution and
 * credential selection are joined so the org's credential decides the host.
 */
async function resolveTargets(
  ctx: GatewayCtx,
  modelStr: string,
): Promise<ResolveOutcome> {
  const candidates = await resolveCandidates(modelStr);
  if (!candidates.length) return { ok: false, reason: "model_not_found" };

  return withOrg(ctx.orgId, async (tx): Promise<ResolveOutcome> => {
    let appId: string | null = null;
    if (ctx.actingAppSlug) {
      const [a] = await tx
        .select()
        .from(apps)
        .where(eq(apps.name, ctx.actingAppSlug))
        .limit(1);
      appId = a?.id ?? null;
    }

    // 1) BYOK credentials (app→org) — first candidate host that has any; all of
    // that host's enabled credentials are failover targets, primary first.
    for (const cand of candidates) {
      const creds = await tx
        .select()
        .from(providerCredentials)
        .where(
          and(
            eq(providerCredentials.provider, cand.host),
            eq(providerCredentials.enabled, true),
          ),
        );
      const appCred = appId
        ? creds.find((c) => c.scopeType === "app" && c.scopeId === appId)
        : undefined;
      const orgCreds = creds.filter((c) => c.scopeType === "org");
      const ordered = [
        ...(appCred ? [appCred] : []),
        ...orgCreds.filter((c) => c.id !== appCred?.id),
      ];
      if (ordered.length > 0) {
        const targets = ordered.map((c) =>
          mkTarget(cand, {
            token: decryptForOrg(ctx.orgId, c.encryptedKey),
            priceOverride: c.priceOverride,
            credentialId: c.id,
            appId,
            options: {
              ...(c.options ?? {}),
              ...(c.region ? { region: c.region } : {}),
            } as ProviderOptions,
          }),
        ) as [Target, ...Target[]];
        return { ok: true, candidates: targets };
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
            return {
              ok: true,
              candidates: [
                mkTarget(cand, {
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
                }),
              ],
            };
          }
        }
      }
    }

    // 3) Env key — first candidate host with a configured key.
    for (const cand of candidates) {
      const provider = getProviderAdapter(cand.host);
      const envKey = provider?.envKey();
      if (envKey)
        return {
          ok: true,
          candidates: [
            mkTarget(cand, {
              token: envKey,
              appId,
              options: provider?.envOptions(),
            }),
          ],
        };
    }
    return { ok: false, reason: "no_credential" };
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

// ── upstream fetch: timeout + single retry / credential failover ──

type FetchSuccess = {
  ok: true;
  resp: Response;
  target: Target;
  /** Abort the upstream request (client disconnect / stream cancel). */
  ctrl: AbortController;
  /** Clear the pending timeout (call once the request is settled/streaming). */
  clearTimer: () => void;
  timedOut: () => boolean;
};
type FetchFailure = {
  ok: false;
  kind: "timeout" | "network";
  error: Error;
  target: Target;
};

/**
 * POST to the upstream with a timeout and at most 2 attempts.
 * - non-stream: total timeout (UPSTREAM_TOTAL_TIMEOUT_MS) covering body read
 *   (the caller keeps the timer armed until the body is consumed).
 * - stream: connect timeout (UPSTREAM_CONNECT_TIMEOUT_MS) only; the caller
 *   clears it on the first body byte.
 * Retries once on a network error or connect timeout, and on a 5xx response
 * (pre-first-byte only; a 5xx prefers the next credential). Never retries
 * 4xx/429 or after streaming has begun.
 */
async function fetchWithFailover(opts: {
  candidates: [Target, ...Target[]];
  streaming: boolean;
  buildRequest: (t: Target) => {
    url: string;
    headers: Record<string, string>;
    body: string;
  };
}): Promise<FetchSuccess | FetchFailure> {
  const MAX_ATTEMPTS = 2;
  let target = opts.candidates[0];
  let lastFailure: FetchFailure | null = null;

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const { url, headers, body } = opts.buildRequest(target);
    const ctrl = new AbortController();
    let timedOut = false;
    const ms = opts.streaming
      ? env.UPSTREAM_CONNECT_TIMEOUT_MS
      : env.UPSTREAM_TOTAL_TIMEOUT_MS;
    const timer = setTimeout(() => {
      timedOut = true;
      ctrl.abort();
    }, ms);

    let resp: Response;
    try {
      resp = await fetch(url, {
        method: "POST",
        headers,
        body,
        signal: ctrl.signal,
      });
    } catch (e) {
      clearTimeout(timer);
      lastFailure = {
        ok: false,
        kind: timedOut ? "timeout" : "network",
        error: e as Error,
        target,
      };
      // Non-stream abort = total timeout → surface 504, don't retry.
      const retryable = opts.streaming || !timedOut;
      if (retryable && attempt < MAX_ATTEMPTS) continue;
      return lastFailure;
    }

    if (resp.status >= 500 && attempt < MAX_ATTEMPTS) {
      clearTimeout(timer);
      void resp.body?.cancel().catch(() => {});
      // 5xx → prefer the next credential for the retry.
      target = opts.candidates[attempt] ?? target;
      continue;
    }

    return {
      ok: true,
      resp,
      target,
      ctrl,
      clearTimer: () => clearTimeout(timer),
      timedOut: () => timedOut,
    };
  }
  /* istanbul ignore next -- loop always returns */
  return lastFailure!;
}

// ── usage finalization (cost + spend + record) ───────────────

async function finalize(
  ctx: GatewayCtx,
  target: Target,
  usage: Usage,
  latencyMs: number,
  status: "success" | "error",
  extra?: { slot?: ConcurrencySlot; estTokens?: number; requestId?: string },
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
  // Reuse the hold's request id when the caller reserved; embeddings and other
  // no-reserve paths settle with a fresh id (nil hold → plain spend commit).
  const rid = extra?.requestId ?? randomUUID();
  try {
    await settleSpend({
      orgId: ctx.orgId,
      teamId: ctx.teamId,
      memberId: ctx.memberId,
      actualMicro: cm,
      requestId: rid,
      usedCredits: target.managed === true,
    });
  } catch (e) {
    // Never silently drop spend accounting — DLQ replays it.
    await recordBillingFailure(
      "spend_settle",
      {
        orgId: ctx.orgId,
        teamId: ctx.teamId,
        memberId: ctx.memberId,
        actualMicro: cm,
        requestId: rid,
        usedCredits: target.managed === true,
      },
      e,
    );
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
    } catch (e) {
      // Served but not billed (wallet short on estimate-under-actual, Redis/DB
      // hiccup, …) — record the debt; the DLQ sweep replays idempotently.
      await recordBillingFailure(
        "credit_spend",
        { orgId: ctx.orgId, costMicro: cm, markupBps: target.markupBps ?? 0, requestId: rid },
        e,
      );
    }
  }
  const usageRow = {
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
    usageEstimated: usage.isEstimated ?? false,
    costMicro: cm,
    status,
    latencyMs,
  };
  try {
    await withOrg(ctx.orgId, (tx) => tx.insert(usageRecords).values(usageRow));
  } catch (e) {
    await recordBillingFailure("usage_insert", usageRow, e);
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

function modelNotFoundError(model: string): GatewayError {
  return {
    kind: "error",
    status: 400,
    body: errBody(
      `The model '${model}' does not exist or is not enabled.`,
      "invalid_request_error",
      "model_not_found",
    ),
  };
}

function noCredentialError(model: string): GatewayError {
  return {
    kind: "error",
    status: 400,
    body: errBody(
      `No provider/credential available for model '${model}'.`,
      "invalid_request_error",
      "model_not_found",
    ),
  };
}

function upstreamFailureError(
  f: FetchFailure,
  headers: Record<string, string>,
): GatewayError {
  if (f.kind === "timeout") {
    return {
      kind: "error",
      status: 504,
      body: errBody("Upstream request timed out.", "api_error", "upstream_timeout"),
      headers,
    };
  }
  return {
    kind: "error",
    status: 502,
    body: errBody(`Upstream request failed: ${f.error.message}`, "api_error"),
    headers,
  };
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

/** 429 result for a denied rate-limit bucket, with limit/reset + Retry-After. */
function rateLimitError(e: RateLimitExceededError): GatewayError {
  const retrySec = Math.max(1, Math.ceil(e.retryAfterMs / 1000));
  const resetSec = Math.max(retrySec, Math.ceil(e.resetMs / 1000));
  return {
    kind: "error",
    status: 429,
    body: errBody(
      `Rate limit exceeded (${e.dimension}, ${e.scope} limit). Retry in ${retrySec}s.`,
      "rate_limit_exceeded",
      "rate_limit_exceeded",
    ),
    headers: {
      "retry-after": String(retrySec),
      "x-ratelimit-limit": String(e.limit),
      "x-ratelimit-remaining": String(e.remaining),
      "x-ratelimit-reset": String(resetSec),
      "ratelimit-limit": String(e.limit),
      "ratelimit-remaining": String(e.remaining),
      "ratelimit-reset": String(resetSec),
    },
  };
}

/** Clear `timer`-style connect timeout on the first upstream body byte. */
function clearOnFirstByte(
  body: ReadableStream<Uint8Array>,
  onFirstByte: () => void,
): ReadableStream<Uint8Array> {
  let seen = false;
  return body.pipeThrough(
    new TransformStream<Uint8Array, Uint8Array>({
      transform(chunk, controller) {
        if (!seen) {
          seen = true;
          onFirstByte();
        }
        controller.enqueue(chunk);
      },
    }),
  );
}

/**
 * Wrap the adapter's output so a downstream cancel (client disconnect) aborts
 * the upstream request and releases the adapter reader. The adapter's finally
 * path then resolves its usage promise → finalize always runs (slot released).
 */
function cancelSafeStream(
  stream: ReadableStream<Uint8Array>,
  abortUpstream: () => void,
): ReadableStream<Uint8Array> {
  const reader = stream.getReader();
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      try {
        const { done, value } = await reader.read();
        if (done) controller.close();
        else controller.enqueue(value);
      } catch (e) {
        controller.error(e);
      }
    },
    async cancel(reason) {
      abortUpstream();
      try {
        await reader.cancel(reason);
      } catch {
        /* already errored */
      }
    },
  });
}

/**
 * Shared governance pre-flight for both the canonical and native-passthrough
 * paths. Order: price → managed-pool priceability (400) → atomic budget+credit
 * hold (402) → rate limit (429) → concurrency (429). The hold is settled by
 * finalize(); EVERY early exit after the reserve releases it (settle at 0).
 * `reserveSpend` throws BudgetExceededError (caught by the router as 402).
 */
type Preflight =
  | { ok: false; result: GatewayError }
  | {
      ok: true;
      headers: Record<string, string>;
      slot: ConcurrencySlot;
      estTokens: number;
      /** The hold's request id — threaded through finalize for settle/dedupe. */
      requestId: string;
      /** Settle the hold at 0 (post-reserve early exits: 429/502/…). */
      releaseHold: () => Promise<void>;
    };

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

  // Managed pool can only serve models it can price — an unpriced model would
  // be billed at 0 (free). Reject rather than serve unmetered managed usage.
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

  const rid = randomUUID();
  // The credit slot holds the raw cost estimate, so scale the balance down by
  // the markup factor: balance/(1+m) − Σholds ≥ 0  ⇔  balance − Σholds·(1+m) ≥ 0.
  let creditBalanceMicro: number | null = null;
  if (target.managed) {
    const balance = await walletBalance(ctx.orgId);
    creditBalanceMicro = Math.floor(balance / (1 + (target.markupBps ?? 0) / 10_000));
  }
  try {
    await reserveSpend({
      orgId: ctx.orgId,
      teamId: ctx.teamId,
      memberId: ctx.memberId,
      estimateMicro: estMicro,
      requestId: rid,
      creditBalanceMicro,
    });
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
    throw e; // BudgetExceededError → 402 upstream (typed mapping in v1/index)
  }
  const releaseHold = () =>
    settleSpend({
      orgId: ctx.orgId,
      teamId: ctx.teamId,
      memberId: ctx.memberId,
      actualMicro: 0,
      requestId: rid,
      usedCredits: target.managed === true,
    }).catch(() => {
      /* hold self-expires (600s) if the release itself fails */
    });

  let rlHeaders: LimitHeaders;
  try {
    rlHeaders = await checkRateLimits({
      orgId: ctx.orgId,
      apiKeyId: ctx.apiKeyId,
      keyRpm: ctx.rateLimitRpm,
      estTokens,
    });
  } catch (e) {
    await releaseHold();
    if (e instanceof RateLimitExceededError)
      return { ok: false, result: rateLimitError(e) };
    throw e;
  }
  const headers = rateHeaders(rlHeaders);

  const slot = await acquireConcurrency(ctx.orgId, ctx.apiKeyId);
  if (!slot.ok) {
    await releaseHold();
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
  return { ok: true, headers, slot, estTokens, requestId: rid, releaseHold };
}

/**
 * Canonical chat handler (hub). Resolves provider/model + credential, enforces
 * budget, calls upstream, meters usage/cost, commits spend, records usage.
 */
export async function handleChat(
  ctx: GatewayCtx,
  canonical: CanonicalChatRequest,
): Promise<ChatResult> {
  const outcome = await resolveTargets(ctx, canonical.model);
  if (!outcome.ok) {
    return outcome.reason === "model_not_found"
      ? modelNotFoundError(canonical.model)
      : noCredentialError(canonical.model);
  }
  const { candidates } = outcome;
  const target = candidates[0];

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
  const { headers, slot, estTokens, requestId, releaseHold } = pf;

  const started = Date.now();
  const attempt = await fetchWithFailover({
    candidates,
    streaming,
    buildRequest: (t) => {
      const wireModel = upstreamId(t);
      const body = provider.adjustBody(
        adapter.toProviderBody(canonical, wireModel, streaming),
        t.family,
      );
      const { url, headers: upstreamHeaders } = provider.resolveEndpoint({
        token: t.token,
        model: wireModel,
        family: t.family,
        capability: adapter.chatCapability,
        stream: streaming,
        options: t.options,
      });
      return { url, headers: upstreamHeaders, body: JSON.stringify(body) };
    },
  });

  if (!attempt.ok) {
    await finalize(
      ctx,
      attempt.target,
      { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      Date.now() - started,
      "error",
      { slot, estTokens, requestId },
    );
    return upstreamFailureError(attempt, headers);
  }

  const { resp, target: served, ctrl, clearTimer, timedOut } = attempt;

  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    clearTimer();
    await finalize(
      ctx,
      served,
      { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      Date.now() - started,
      "error",
      { slot, estTokens, requestId },
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
      clearTimer();
      await slot.release();
      await releaseHold();
      return {
        kind: "error",
        status: 502,
        body: errBody("Upstream returned no stream body.", "api_error"),
        headers,
      };
    }
    // Connect-only timeout: cleared on the first upstream byte.
    const upstream = clearOnFirstByte(resp.body, clearTimer);
    const { stream, usage } = adapter.streamTransform(
      provider.wrapStream(upstream, served.family),
      served.model,
    );
    // Finalize (release slot + meter) once the stream is fully consumed or
    // aborted — the adapter's finally path resolves `usage` either way.
    void usage.then((u) =>
      finalize(ctx, served, u, Date.now() - started, "success", {
        slot,
        estTokens,
        requestId,
      }),
    );
    const out = cancelSafeStream(stream, () => {
      clearTimer();
      ctrl.abort();
    });
    return { kind: "stream", stream: out, model: served.model, headers };
  }

  // Non-stream: the total timeout stays armed until the body is fully read.
  let json: unknown;
  try {
    json = await resp.json();
  } catch {
    clearTimer();
    await finalize(
      ctx,
      served,
      { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      Date.now() - started,
      "error",
      { slot, estTokens, requestId },
    );
    if (timedOut()) {
      return upstreamFailureError(
        { ok: false, kind: "timeout", error: new Error("body timeout"), target: served },
        headers,
      );
    }
    return {
      kind: "error",
      status: 502,
      body: errBody("Upstream returned an unreadable body.", "api_error"),
      headers,
    };
  }
  clearTimer();
  const { openai, usage } = adapter.fromProviderResponse(json, served.model);
  await finalize(ctx, served, usage, Date.now() - started, "success", {
    slot,
    estTokens,
    requestId,
  });
  return { kind: "json", openai, headers };
}

// ── embeddings (direct proxy + metering) ─────────────────────

export async function handleEmbeddings(
  ctx: GatewayCtx,
  req: { model: string; input: unknown } & Record<string, unknown>,
): Promise<ChatResult> {
  const outcome = await resolveTargets(ctx, req.model);
  if (!outcome.ok) {
    return outcome.reason === "model_not_found"
      ? modelNotFoundError(req.model)
      : noCredentialError(req.model);
  }
  const { candidates } = outcome;
  const target = candidates[0];
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

  const started = Date.now();
  const attempt = await fetchWithFailover({
    candidates,
    streaming: false,
    buildRequest: (t) => {
      const wireModel = upstreamId(t);
      const { url, headers } = providerFor(t).resolveEndpoint({
        token: t.token,
        model: wireModel,
        family: t.family,
        capability: "embeddings",
        stream: false,
        options: t.options,
      });
      return { url, headers, body: JSON.stringify({ ...req, model: wireModel }) };
    },
  });

  if (!attempt.ok) {
    await finalize(
      ctx,
      attempt.target,
      { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      Date.now() - started,
      "error",
      { slot, estTokens: 0 },
    );
    return upstreamFailureError(attempt, rHeaders);
  }

  const { resp, target: served, clearTimer, timedOut } = attempt;

  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    clearTimer();
    await finalize(
      ctx,
      served,
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

  let json: any;
  try {
    json = await resp.json();
  } catch {
    clearTimer();
    await finalize(
      ctx,
      served,
      { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      Date.now() - started,
      "error",
      { slot, estTokens: 0 },
    );
    if (timedOut()) {
      return upstreamFailureError(
        { ok: false, kind: "timeout", error: new Error("body timeout"), target: served },
        rHeaders,
      );
    }
    return {
      kind: "error",
      status: 502,
      body: errBody("Upstream returned an unreadable body.", "api_error"),
      headers: rHeaders,
    };
  }
  clearTimer();
  const usage: Usage = {
    promptTokens: json.usage?.prompt_tokens ?? 0,
    completionTokens: 0,
    totalTokens: json.usage?.total_tokens ?? json.usage?.prompt_tokens ?? 0,
  };
  await finalize(ctx, served, usage, Date.now() - started, "success", {
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
  const outcome = await resolveTargets(ctx, n.model);
  if (!outcome.ok) {
    return outcome.reason === "model_not_found"
      ? modelNotFoundError(n.model)
      : noCredentialError(n.model);
  }
  const { candidates } = outcome;
  const target = candidates[0];

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
  const { headers, slot, estTokens, requestId, releaseHold } = pf;

  const provider = providerFor(target);
  const adapter = getAdapter(target.family);

  const started = Date.now();
  const attempt = await fetchWithFailover({
    candidates,
    streaming: n.stream,
    buildRequest: (t) => {
      const wireModel = upstreamId(t);
      let body: Record<string, unknown> = { ...n.rawBody, model: wireModel };
      // Meter OpenAI-family Chat streaming via the trailing usage chunk.
      if (
        n.stream &&
        t.family === "openai" &&
        n.capability === "chat" &&
        body.stream_options == null
      ) {
        body.stream_options = { include_usage: true };
      }
      body = provider.adjustBody(body, t.family);
      const { url, headers: upstreamHeaders } = provider.resolveEndpoint({
        token: t.token,
        model: wireModel,
        family: t.family,
        capability: n.capability,
        stream: n.stream,
        options: t.options,
      });
      return {
        url,
        headers: { ...upstreamHeaders, ...(n.extraHeaders ?? {}) },
        body: JSON.stringify(body),
      };
    },
  });

  if (!attempt.ok) {
    await finalize(
      ctx,
      attempt.target,
      { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      Date.now() - started,
      "error",
      { slot, estTokens, requestId },
    );
    return upstreamFailureError(attempt, headers);
  }

  const { resp, target: served, ctrl, clearTimer, timedOut } = attempt;

  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    clearTimer();
    await finalize(
      ctx,
      served,
      { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      Date.now() - started,
      "error",
      { slot, estTokens, requestId },
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
      clearTimer();
      await slot.release();
      await releaseHold();
      return {
        kind: "error",
        status: 502,
        body: errBody("Upstream returned no stream body.", "api_error"),
        headers,
      };
    }
    // Connect-only timeout: cleared on the first upstream byte.
    // Bedrock event-stream → Anthropic SSE; every other host is byte-identical.
    // tee: one branch to the client verbatim, one to the read-only usage sniffer.
    const client = provider.wrapStream(
      clearOnFirstByte(resp.body, clearTimer),
      served.family,
    );
    const [toClient, toMeter] = client.tee();
    const usage = adapter.sniffStreamUsage(toMeter, n.capability);
    void usage.then((u) =>
      finalize(ctx, served, u, Date.now() - started, "success", {
        slot,
        estTokens,
        requestId,
      }),
    );
    // Client cancel → abort upstream; the sniffer then ends (best-effort usage)
    // and finalize still runs (slot released, hold settled).
    const out = cancelSafeStream(toClient, () => {
      clearTimer();
      ctrl.abort();
    });
    return { kind: "stream", stream: out, headers };
  }

  // Non-stream: the total timeout stays armed until the body is fully read.
  let json: unknown;
  try {
    json = await resp.json();
  } catch {
    clearTimer();
    await finalize(
      ctx,
      served,
      { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      Date.now() - started,
      "error",
      { slot, estTokens, requestId },
    );
    if (timedOut()) {
      return upstreamFailureError(
        { ok: false, kind: "timeout", error: new Error("body timeout"), target: served },
        headers,
      );
    }
    return {
      kind: "error",
      status: 502,
      body: errBody("Upstream returned an unreadable body.", "api_error"),
      headers,
    };
  }
  clearTimer();
  const usage = adapter.parseUsage(json, n.capability);
  await finalize(ctx, served, usage, Date.now() - started, "success", {
    slot,
    estTokens,
    requestId,
  });
  return { kind: "json", json, headers };
}

// Native usage extraction (streamed + non-streamed) now lives on the family
// adapter (sniffStreamUsage / parseUsage) — see @vortex/core providers/families.
