import { createMiddleware } from "hono/factory";
import { eq } from "drizzle-orm";
import { withBypass, apiKeys, memberships } from "@vortex/db";
import { hashApiKey } from "../features/keys/keys.util.js";

// Gateway request context resolved from the virtual key.
export type GatewayCtx = {
  apiKeyId: string;
  orgId: string;
  memberId: string;
  teamId: string | null;
  /** Custom per-key RPM cap (null = plan default only). */
  rateLimitRpm: number | null;
  /** `x-vortex-user` — human this app is acting on behalf of (attribution). */
  actingUserId: string | null;
  /** `x-vortex-app` — acting app slug/name (attribution). */
  actingAppSlug: string | null;
};

export type GatewayEnv = {
  Variables: {
    gateway: GatewayCtx;
  };
};

function readBearer(c: {
  req: { header: (n: string) => string | undefined };
}): string | null {
  const auth = c.req.header("authorization");
  if (auth?.toLowerCase().startsWith("bearer ")) return auth.slice(7).trim();
  const x = c.req.header("x-api-key");
  return x?.trim() || null;
}

function err(message: string, type: string) {
  return { error: { message, type, param: null, code: null } };
}

/**
 * Authenticate a `vtx_` virtual key (Bearer or x-api-key), resolve its owner
 * membership, and attach the gateway context. Rejects 401 on any failure.
 */
export const gatewayAuth = createMiddleware<GatewayEnv>(async (c, next) => {
  const plaintext = readBearer(c);
  if (!plaintext) {
    return c.json(err("Missing API key.", "authentication_error"), 401);
  }
  const keyHash = hashApiKey(plaintext);

  const resolved = await withBypass(async (tx) => {
    const [row] = await tx
      .select({ k: apiKeys, m: memberships })
      .from(apiKeys)
      .leftJoin(memberships, eq(memberships.id, apiKeys.ownerMemberId))
      .where(eq(apiKeys.keyHash, keyHash))
      .limit(1);
    return row ? { k: row.k, m: row.m } : null;
  });

  if (!resolved?.k) {
    return c.json(err("Invalid API key.", "authentication_error"), 401);
  }
  const { k, m } = resolved;
  if (k.status !== "active") {
    return c.json(err("API key is not active.", "authentication_error"), 401);
  }
  if (k.expiresAt && k.expiresAt.getTime() <= Date.now()) {
    return c.json(err("API key has expired.", "authentication_error"), 401);
  }

  c.set("gateway", {
    apiKeyId: k.id,
    orgId: k.orgId,
    memberId: k.ownerMemberId,
    teamId: m?.teamId ?? null,
    rateLimitRpm: k.rateLimitRpm ?? null,
    actingUserId: c.req.header("x-vortex-user")?.trim() || null,
    actingAppSlug: c.req.header("x-vortex-app")?.trim() || null,
  });

  await next();
});
