import { Hono } from "hono";
import { z } from "zod";
import { eq, and } from "drizzle-orm";
import { withOrg, teams } from "@vortex/db";
import { createTeamSchema, budgetEnforcementSchema } from "@vortex/shared";
import { type AppEnv, requireMember } from "../../shared/ctx.js";
import { requireRole } from "../../shared/rbac.js";

const updateTeamSchema = z.object({
  name: z.string().min(1).optional(),
  defaultMemberBudgetMicro: z.number().int().nullish(),
  budgetEnforcement: budgetEnforcementSchema.optional(),
});

export const teams_ = new Hono<AppEnv>();
teams_.use("*", requireMember);

// GET / — list this org's teams.
teams_.get("/", async (c) => {
  const { orgId } = c.get("member");
  const rows = await withOrg(orgId, (tx) => tx.select().from(teams));
  return c.json(rows);
});

// POST / — create a team (owner/admin).
teams_.post("/", async (c) => {
  const forbidden = requireRole(c, ["owner", "admin"]);
  if (forbidden) return forbidden;
  const { orgId } = c.get("member");
  const body = createTeamSchema.parse(await c.req.json());
  const [team] = await withOrg(orgId, (tx) =>
    tx
      .insert(teams)
      .values({
        orgId,
        name: body.name,
        defaultMemberBudgetMicro: body.defaultMemberBudgetMicro ?? null,
        budgetEnforcement: body.budgetEnforcement ?? "hard",
      })
      .returning(),
  );
  return c.json(team, 201);
});

// PATCH /:id — update name / budget defaults (owner/admin).
teams_.patch("/:id", async (c) => {
  const forbidden = requireRole(c, ["owner", "admin"]);
  if (forbidden) return forbidden;
  const { orgId } = c.get("member");
  const id = c.req.param("id");
  const body = updateTeamSchema.parse(await c.req.json());

  const patch: Record<string, unknown> = {};
  if (body.name !== undefined) patch.name = body.name;
  if (body.defaultMemberBudgetMicro !== undefined)
    patch.defaultMemberBudgetMicro = body.defaultMemberBudgetMicro;
  if (body.budgetEnforcement !== undefined)
    patch.budgetEnforcement = body.budgetEnforcement;
  if (Object.keys(patch).length === 0)
    return c.json({ error: "no_fields" }, 400);

  const [team] = await withOrg(orgId, (tx) =>
    tx
      .update(teams)
      .set(patch)
      .where(and(eq(teams.id, id), eq(teams.orgId, orgId)))
      .returning(),
  );
  if (!team) return c.json({ error: "not_found" }, 404);
  return c.json(team);
});

export { teams_ as teams };
