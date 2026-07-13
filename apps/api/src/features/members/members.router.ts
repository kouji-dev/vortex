import { Hono } from "hono";
import { z } from "zod";
import { eq, and, sql } from "drizzle-orm";
import { withOrg, memberships } from "@vortex/db";
import { orgRoleSchema, teamRoleSchema } from "@vortex/shared";
import { type AppEnv, requireMember } from "../../shared/ctx.js";
import {
  isOrgManager,
  requireOrgManager,
  assertTeamInOrg,
} from "../../shared/rbac.js";
import { parsePage, pageEnvelope } from "../../shared/pagination.js";

const updateMemberSchema = z.object({
  role: orgRoleSchema.optional(),
  teamId: z.string().nullable().optional(),
  teamRole: teamRoleSchema.nullable().optional(),
  budgetOverrideMicro: z.number().int().nonnegative().nullish(),
});

export const members = new Hono<AppEnv>();
members.use("*", requireMember);

// GET / — list memberships (human + technical) in the org. Managers see the
// full rows; plain members get a redacted directory view.
members.get("/", async (c) => {
  const member = c.get("member");
  const page = parsePage(c);
  const rows = await withOrg(member.orgId, async (tx) => {
    if (isOrgManager(member)) {
      return tx
        .select()
        .from(memberships)
        .limit(page.limit)
        .offset(page.offset);
    }
    return tx
      .select({
        id: memberships.id,
        type: memberships.type,
        role: memberships.role,
        teamId: memberships.teamId,
        teamRole: memberships.teamRole,
      })
      .from(memberships)
      .limit(page.limit)
      .offset(page.offset);
  });
  return c.json(pageEnvelope(rows, page));
});

// PATCH /:id — role / team / budget override (owner/admin).
members.patch("/:id", async (c) => {
  const forbidden = requireOrgManager(c);
  if (forbidden) return forbidden;
  const { orgId } = c.get("member");
  const id = c.req.param("id");
  const parsed = updateMemberSchema.safeParse(await c.req.json().catch(() => ({})));
  if (!parsed.success)
    return c.json({ error: "invalid_body", details: parsed.error.flatten() }, 400);
  const body = parsed.data;

  // Load the target first: 404 on missing/cross-org, and we need its current
  // state for the last-owner + team-role checks.
  const target = await withOrg(orgId, async (tx) => {
    const [row] = await tx
      .select()
      .from(memberships)
      .where(and(eq(memberships.id, id), eq(memberships.orgId, orgId)))
      .limit(1);
    return row ?? null;
  });
  if (!target) return c.json({ error: "not_found" }, 404);

  // Demoting the last remaining owner would orphan the org.
  if (
    body.role !== undefined &&
    body.role !== "owner" &&
    target.role === "owner"
  ) {
    const owners = await withOrg(orgId, async (tx) => {
      const [row] = await tx
        .select({ n: sql<number>`count(*)::int` })
        .from(memberships)
        .where(and(eq(memberships.orgId, orgId), eq(memberships.role, "owner")));
      return row?.n ?? 0;
    });
    if (owners <= 1) return c.json({ error: "last_owner" }, 409);
  }

  // Moving into a team → the team must exist in this org.
  if (body.teamId != null) {
    const team = await withOrg(orgId, (tx) =>
      assertTeamInOrg(tx, orgId, body.teamId!),
    );
    if (!team) return c.json({ error: "team_not_in_org" }, 400);
  }

  // A team role only makes sense with an (effective) team.
  const effectiveTeamId =
    body.teamId !== undefined ? body.teamId : target.teamId;
  if (body.teamRole != null && effectiveTeamId == null)
    return c.json({ error: "team_role_without_team" }, 400);

  const patch: Record<string, unknown> = {};
  if (body.role !== undefined) patch.role = body.role;
  if (body.teamId !== undefined) patch.teamId = body.teamId;
  if (body.teamRole !== undefined) patch.teamRole = body.teamRole;
  if (body.budgetOverrideMicro !== undefined)
    patch.budgetOverrideMicro = body.budgetOverrideMicro;
  if (Object.keys(patch).length === 0)
    return c.json({ error: "no_fields" }, 400);

  const [member] = await withOrg(orgId, (tx) =>
    tx
      .update(memberships)
      .set(patch)
      .where(and(eq(memberships.id, id), eq(memberships.orgId, orgId)))
      .returning(),
  );
  if (!member) return c.json({ error: "not_found" }, 404);
  return c.json(member);
});
