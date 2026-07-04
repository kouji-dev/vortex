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

export const requireAuth = createMiddleware<AppEnv>(async (c, next) => {
  if (!c.get("user")) return c.json({ error: "unauthorized" }, 401);
  await next();
});

/** Require an authenticated, provisioned member; attaches org context. */
export const requireMember = createMiddleware<AppEnv>(async (c, next) => {
  const user = c.get("user");
  if (!user) return c.json({ error: "unauthorized" }, 401);
  const member = await getMembership(user.id);
  if (!member) return c.json({ error: "not_provisioned" }, 409);
  c.set("member", member);
  await next();
});
