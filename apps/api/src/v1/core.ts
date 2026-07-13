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

type ResolveOutcome =
  | { ok: true; candidates: [Target, ...Target[]] }
  | { ok: false; reason: "model_not_found" | "no_credential" };

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
    case "groq":
      return env.GROQ_API_KEY;
    case "mistral":
      return env.MISTRAL_API_KEY;
    case "deepseek":
      return env.DEEPSEEK_API_KEY;
    case "xai":
      return env.XAI_API_KEY;
    case "together":
      return env.TOGETHER_API_KEY;
    case "fireworks":
      return env.FIREWORKS_API_KEY;
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

/**
 * Resolve `{provider, model}` from a request model string.
 * Returns null when the model can't be mapped to an enabled provider
 * (unknown model → 400, never silently routed to an arbitrary provider).
 */
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
  // 1) exact catalog match (in-memory, cached), 2) model-family inference.
  const rows = (await catalogRows()).filter((r) => r.modelName === modelStr);
  const hit = rows.find((r) => enabled.includes(r.provider));
  if (hit) return { provider: hit.provider, model: modelStr };
  const inferred = inferProvider(modelStr);
  if (inferred && enabled.includes(inferred))
    return { provider: inferred, model: modelStr };
  return null;
}

function credToTarget(
  orgId: string,
  cred: typeof providerCredentials.$inferSelect,
  provider: string,
  model: string,
  appId: string | null,
): Target {
  return {
    provider,
    model,
    token: decryptForOrg(orgId, cred.encryptedKey),
    priceOverride: cred.priceOverride,
    credentialId: cred.id,
    appId,
    options: {
      ...(cred.options ?? {}),
      ...(cred.region ? { region: cred.region } : {}),
    } as ProviderOptions,
  };
}

/**
 * Resolve failover candidates for a model: the primary credential (app-scoped
 * preferred, then org-scoped) followed by every other enabled org credential
 * for the same provider. Falls back to managed pool / env key (single
 * candidate) when the org holds no BYOK credential.
 */
async function resolveTargets(
  ctx: GatewayCtx,
  modelStr: string,
): Promise<ResolveOutcome> {
  const resolved = await resolveModel(modelStr);
  if (!resolved) return { ok: false, reason: "model_not_found" };
  const { provider, model } = resolved;

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

    // All enabled credentials for this provider in one query; order the
    // primary first (app-scoped for the acting app > org-scoped).
    const creds = await tx
      .select()
      .from(providerCredentials)
      .where(
        and(
          eq(providerCredentials.provider, provider),
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
      const candidates = ordered.map((c) =>
        credToTarget(ctx.orgId, c, provider, model, appId),
      ) as [Target, ...Target[]];
      return { ok: true, candidates };
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
            ok: true,
            candidates: [
              {
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
              },
            ],
          };
        }
      }
    }

    const envKey = envKeyFor(provider);
    if (!envKey) return { ok: false, reason: "no_credential" };
    return {
      ok: true,
      candidates: [
        {
          provider,
          model,
          token: envKey,
          appId,
          options: envOptionsFor(provider),
        },
      ],
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
  buildBody: (t: Target) => string;
  capability: Capability;
}): Promise<FetchSuccess | FetchFailure> {
  const MAX_ATTEMPTS = 2;
  let target = opts.candidates[0];
  let lastFailure: FetchFailure | null = null;

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const { url, headers } = buildUpstream({
      provider: target.provider,
      model: target.model,
      capability: opts.capability,
      streaming: opts.streaming,
      token: target.token,
      options: target.options,
    });
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
        body: opts.buildBody(target),
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

function errBody(message: string, type: string, code?: string) {
  return { error: { message, type, param: null, code: code ?? null } };
}

function modelNotFoundError(model: string): ChatResult {
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

function noCredentialError(model: string): ChatResult {
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
): ChatResult {
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
function rateLimitError(e: RateLimitExceededError): ChatResult {
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

  // Governance order: budget+credits (atomic hold, 402) → rate limit (RPM/TPM,
  // 429) → concurrency (429) → proxy. The hold is settled by finalize(); every
  // early exit after the reserve must release it (settle at 0).
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
        kind: "error",
        status: 402,
        body: errBody("Managed credits exhausted.", "insufficient_quota", "credits_exhausted"),
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
    if (e instanceof RateLimitExceededError) return rateLimitError(e);
    throw e;
  }
  const headers = rateHeaders(rlHeaders);

  const slot = await acquireConcurrency(ctx.orgId, ctx.apiKeyId);
  if (!slot.ok) {
    await releaseHold();
    return {
      kind: "error",
      status: 429,
      body: errBody("Too many concurrent requests.", "rate_limit_exceeded", "concurrency_limit"),
      headers: { ...headers, "retry-after": "1" },
    };
  }

  const started = Date.now();
  const attempt = await fetchWithFailover({
    candidates,
    streaming,
    capability: adapter.chatCapability,
    buildBody: (t) =>
      JSON.stringify(adapter.toProviderBody(canonical, t.model, streaming)),
  });

  if (!attempt.ok) {
    await finalize(
      ctx,
      attempt.target,
      { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      Date.now() - started,
      "error",
      { slot, estTokens, requestId: rid },
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
      { slot, estTokens, requestId: rid },
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
    const { stream, usage } = adapter.streamTransform(upstream, served.model);
    // Finalize (release slot + meter) once the stream is fully consumed or
    // aborted — the adapter's finally path resolves `usage` either way.
    void usage.then((u) =>
      finalize(ctx, served, u, Date.now() - started, "success", {
        slot,
        estTokens,
        requestId: rid,
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
      { slot, estTokens, requestId: rid },
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
    requestId: rid,
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
    capability: "embeddings",
    buildBody: (t) => JSON.stringify({ ...req, model: t.model }),
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
