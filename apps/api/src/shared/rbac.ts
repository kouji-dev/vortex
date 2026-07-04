import type { Context } from "hono";
import type { AppEnv } from "./ctx.js";

/**
 * Guard a handler by org role. Returns a 403 `Response` to return early, or
 * `null` when the caller's role is allowed.
 *
 *   const forbidden = requireRole(c, ["owner", "admin"]);
 *   if (forbidden) return forbidden;
 */
export function requireRole(
  c: Context<AppEnv>,
  roles: string[],
): Response | null {
  const member = c.get("member");
  if (!member || !roles.includes(member.role)) {
    return c.json({ error: "forbidden" }, 403);
  }
  return null;
}
