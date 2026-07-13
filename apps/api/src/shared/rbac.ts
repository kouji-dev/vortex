import type { Context } from "hono";
import { and, eq } from "drizzle-orm";
import { memberships, teams, type Db, type Tx } from "@vortex/db";
import type { AppEnv, PlatformRole } from "./ctx.js";
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

/**
 * Guard a handler to org owner/admin. Returns a 403 `Response` to return
 * early, or `null` when the caller may manage the org.
 *
 *   const forbidden = requireOrgManager(c);
 *   if (forbidden) return forbidden;
 */
export function requireOrgManager(c: Context<AppEnv>): Response | null {
  return isOrgManager(c.get("member"))
    ? null
    : c.json({ error: "forbidden" }, 403);
}

/**
 * Guard a handler to callers who may manage *this* team (org owner/admin, or
 * a `team_admin` of the team). Returns a 403 `Response`, or `null` when allowed.
 */
export function requireTeamManager(
  c: Context<AppEnv>,
  teamId: string,
): Response | null {
  return canManageTeam(c.get("member"), teamId)
    ? null
    : c.json({ error: "forbidden" }, 403);
}

/**
 * Guard a platform handler by platform role. Reads `platformRole` from ctx
 * (set by `requirePlatformAdmin` on the /platform/* surface). Returns a 403
 * `Response` to return early, or `null` when the caller's role is allowed.
 *
 *   const forbidden = requirePlatformRole(c, ["platform_owner", "platform_admin"]);
 *   if (forbidden) return forbidden;
 */
export function requirePlatformRole(
  c: Context<AppEnv>,
  roles: PlatformRole[],
): Response | null {
  const role = c.get("platformRole");
  if (!role || !roles.includes(role)) {
    return c.json({ error: "forbidden" }, 403);
  }
  return null;
}

/**
 * Assert a membership belongs to the given org. Returns the membership row,
 * or `null` when it doesn't exist or lives in another org (treat as 404).
 */
export async function assertMemberInOrg(
  dbOrTx: Db | Tx,
  orgId: string,
  memberId: string,
): Promise<typeof memberships.$inferSelect | null> {
  const [row] = await dbOrTx
    .select()
    .from(memberships)
    .where(and(eq(memberships.id, memberId), eq(memberships.orgId, orgId)))
    .limit(1);
  return row ?? null;
}

/**
 * Assert a team belongs to the given org. Returns the team row, or `null`
 * when it doesn't exist or lives in another org (treat as 404).
 */
export async function assertTeamInOrg(
  dbOrTx: Db | Tx,
  orgId: string,
  teamId: string,
): Promise<typeof teams.$inferSelect | null> {
  const [row] = await dbOrTx
    .select()
    .from(teams)
    .where(and(eq(teams.id, teamId), eq(teams.orgId, orgId)))
    .limit(1);
  return row ?? null;
}
