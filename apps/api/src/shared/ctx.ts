import type { Context } from "hono";
import { createMiddleware } from "hono/factory";
import { auth } from "./auth.js";
import {
  getMembership,
  type MemberContext,
} from "../features/provisioning/provisioning.service.js";

export type AuthUser = { id: string; email: string; name?: string | null };

export type AppEnv = {
  Variables: {
    user: AuthUser | null;
    member: MemberContext;
  };
};

/** Load the better-auth session (if any) onto the context. */
export const sessionMw = createMiddleware<AppEnv>(async (c, next) => {
  const session = await auth.api.getSession({ headers: c.req.raw.headers });
  c.set(
    "user",
    session?.user
      ? {
          id: session.user.id,
          email: session.user.email,
          name: session.user.name,
        }
      : null,
  );
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
 *  Same auth gate as requireAuth (401), then requires a membership (409). */
export const requireMember = createMiddleware<AppEnv>(async (c, next) => {
  const denied = authGate(c);
  if (denied) return denied;
  const member = await getMembership(c.get("user")!.id);
  if (!member) return c.json({ error: "not_provisioned" }, 409);
  c.set("member", member);
  await next();
});
