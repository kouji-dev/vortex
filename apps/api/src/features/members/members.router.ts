import { Hono } from "hono";
import { z } from "zod";
import { eq, and } from "drizzle-orm";
import { withOrg, memberships } from "@vortex/db";
import { orgRoleSchema, teamRoleSchema } from "@vortex/shared";
import { type AppEnv, requireMember } from "../../shared/ctx.js";
import { requireRole } from "../../shared/rbac.js";

const updateMemberSchema = z.object({
  role: orgRoleSchema.optional(),
  teamId: z.string().nullable().optional(),
  teamRole: teamRoleSchema.nullable().optional(),
  budgetOverrideMicro: z.number().int().nullish(),
});

export const members = new Hono<AppEnv>();
members.use("*", requireMember);

// GET / — list every membership (human + technical) in the org.
members.get("/", async (c) => {
  const { orgId } = c.get("member");
  const rows = await withOrg(orgId, (tx) => tx.select().from(memberships));
  return c.json(rows);
});

// PATCH /:id — role / team / budget override (owner/admin).
members.patch("/:id", async (c) => {
  const forbidden = requireRole(c, ["owner", "admin"]);
  if (forbidden) return forbidden;
  const { orgId } = c.get("member");
  const id = c.req.param("id");
  const body = updateMemberSchema.parse(await c.req.json());

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
