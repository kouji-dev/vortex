import type { Context } from "hono";
import type { AppEnv } from "./ctx.js";
import type { MemberContext } from "../features/provisioning/provisioning.service.js";

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

/** Org owner/admin manage everything in the org. */
export function isOrgManager(member: MemberContext | undefined): boolean {
  return member?.role === "owner" || member?.role === "admin";
}

/**
 * May the caller edit this team? Org owner/admin, or a `team_admin` of *this*
 * team. A plain team member (or an admin of a different team) may not.
 */
export function canManageTeam(
  member: MemberContext | undefined,
  teamId: string,
): boolean {
  if (isOrgManager(member)) return true;
  return member?.teamId === teamId && member?.teamRole === "team_admin";
}
