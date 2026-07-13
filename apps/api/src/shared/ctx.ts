import type { Context } from "hono";
import { createMiddleware } from "hono/factory";
import { and, eq } from "drizzle-orm";
import { withBypass, apiKeys, memberships, users } from "@vortex/db";
import { auth } from "./auth.js";
import { hashApiKey } from "../features/keys/keys.util.js";
import {
  getMembership,
  type MemberContext,
} from "../features/provisioning/provisioning.service.js";

export type AuthUser = { id: string; email: string; name?: string | null };

export type PlatformRole = "platform_owner" | "platform_admin" | "support";

export type AppEnv = {
  Variables: {
    user: AuthUser | null;
    member: MemberContext;
    /** Set by the platform surface after the platform_admins lookup. */
    platformRole: PlatformRole | null;
  };
};

/** Extract a `vtx_` key from `Authorization: Bearer` or `x-api-key`. */
function readBearerKey(headers: Headers): string | null {
  const a = headers.get("authorization");
  if (a?.toLowerCase().startsWith("bearer ")) return a.slice(7).trim();
  return headers.get("x-api-key")?.trim() || null;
}

/**
 * Resolve an API key into the same identity a session would produce: the key's
 * owner membership (with its role) → programmatic access to /api/* without a
 * login. Returns null when no/invalid/inactive/expired key is present.
 */
async function apiKeyPrincipal(
  headers: Headers,
): Promise<{ user: AuthUser; member: MemberContext } | null> {
  const plaintext = readBearerKey(headers);
  if (!plaintext) return null;
  const keyHash = hashApiKey(plaintext);

  const row = await withBypass(async (tx) => {
    const [r] = await tx
      .select({
        expiresAt: apiKeys.expiresAt,
        m: memberships,
        userEmail: users.email,
        userName: users.name,
      })
      .from(apiKeys)
      .leftJoin(memberships, eq(memberships.id, apiKeys.ownerMemberId))
      .leftJoin(users, eq(users.id, memberships.userId))
      // Only an active key matches — revoked (incl. rotated-out) / disabled keys
      // are filtered at the source and never reach the checks below.
      .where(and(eq(apiKeys.keyHash, keyHash), eq(apiKeys.status, "active")))
      .limit(1);
    return r ?? null;
  });

  if (!row?.m) return null;
  if (row.expiresAt && row.expiresAt.getTime() <= Date.now()) return null;

  const m = row.m;
  const member: MemberContext = {
    membershipId: m.id,
    orgId: m.orgId,
    role: (m.role ?? "member") as MemberContext["role"],
    teamId: m.teamId,
    teamRole: m.teamRole as MemberContext["teamRole"],
  };
  // Human key → acts as the user. Technical (service-account) key → no user row.
  const user: AuthUser = m.userId
    ? { id: m.userId, email: row.userEmail ?? "", name: row.userName ?? null }
    : { id: `svc:${m.id}`, email: `service+${m.id}@vortex.local`, name: "service account" };

  return { user, member };
}

/** Resolve the better-auth session user (if any). */
async function sessionUser(c: Context<AppEnv>): Promise<AuthUser | null> {
  const session = await auth.api.getSession({ headers: c.req.raw.headers });
  return session?.user
    ? { id: session.user.id, email: session.user.email, name: session.user.name }
    : null;
}

/**
 * Session-only identity. Used for the platform super-admin surface (/platform/*),
 * which is deliberately NOT reachable with an API key — super-admin actions
 * require an interactive dashboard login, never a programmatic key.
 */
export const sessionMw = createMiddleware<AppEnv>(async (c, next) => {
  c.set("user", await sessionUser(c));
  await next();
});

/**
 * Org API identity (/api/*): better-auth session first, then a `vtx_` API key
 * for programmatic/headless access. A key pre-resolves its owner member context,
 * so role gating (requireRole) applies exactly as it would for that member —
 * a member-role key cannot perform owner/admin-only operations.
 */
export const apiAuthMw = createMiddleware<AppEnv>(async (c, next) => {
  const u = await sessionUser(c);
  if (u) {
    c.set("user", u);
    return next();
  }

  const principal = await apiKeyPrincipal(c.req.raw.headers);
  if (principal) {
    c.set("user", principal.user);
    c.set("member", principal.member);
    return next();
  }

  c.set("user", null);
  await next();
});

/** The single auth gate: 401 Response when signed out, else null. */
const authGate = (c: Context<AppEnv>): Response | null =>
  c.get("user") ? null : c.json({ error: "unauthorized" }, 401);

export const requireAuth = createMiddleware<AppEnv>(async (c, next) => {
  const denied = authGate(c);
  if (denied) return denied;
  await next();
});

/** Require an authenticated, provisioned member; attaches org context.
 *  Same auth gate as requireAuth (401), then requires a membership (409).
 *  A key-authed request already carries its member — reuse it (no re-lookup). */
export const requireMember = createMiddleware<AppEnv>(async (c, next) => {
  const denied = authGate(c);
  if (denied) return denied;
  let member = c.get("member");
  if (!member) {
    const found = await getMembership(c.get("user")!.id);
    if (!found) return c.json({ error: "not_provisioned" }, 409);
    member = found;
  }
  c.set("member", member);
  await next();
});
