import { Hono } from "hono";
import { z } from "zod";
import { eq, and } from "drizzle-orm";
import { withOrg, teams } from "@vortex/db";
import { createTeamSchema, budgetEnforcementSchema } from "@vortex/shared";
import { type AppEnv, requireMember } from "../../shared/ctx.js";
import { requireOrgManager, requireTeamManager } from "../../shared/rbac.js";
import { parsePage, pageEnvelope } from "../../shared/pagination.js";

const updateTeamSchema = z.object({
  name: z.string().min(1).optional(),
  budgetMicro: z.number().int().nonnegative().nullish(),
  defaultMemberBudgetMicro: z.number().int().nonnegative().nullish(),
  budgetEnforcement: budgetEnforcementSchema.optional(),
});

export const teams_ = new Hono<AppEnv>();
teams_.use("*", requireMember);

// GET / — list this org's teams.
teams_.get("/", async (c) => {
  const { orgId } = c.get("member");
  const page = parsePage(c);
  const rows = await withOrg(orgId, (tx) =>
    tx.select().from(teams).limit(page.limit).offset(page.offset),
  );
  return c.json(pageEnvelope(rows, page));
});

// POST / — create a team (owner/admin).
teams_.post("/", async (c) => {
  const forbidden = requireOrgManager(c);
  if (forbidden) return forbidden;
  const { orgId } = c.get("member");
  const parsed = createTeamSchema.safeParse(await c.req.json().catch(() => ({})));
  if (!parsed.success)
    return c.json({ error: "invalid_body", details: parsed.error.flatten() }, 400);
  const body = parsed.data;
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

// PATCH /:id — rename (org owner/admin, or this team's team_admin). Budget
// fields (budgetMicro / defaultMemberBudgetMicro / budgetEnforcement) are
// org-manager only — a team_admin may not raise their own team's budget.
teams_.patch("/:id", async (c) => {
  const id = c.req.param("id");
  const forbidden = requireTeamManager(c, id);
  if (forbidden) return forbidden;
  const { orgId } = c.get("member");
  const parsed = updateTeamSchema.safeParse(await c.req.json().catch(() => ({})));
  if (!parsed.success)
    return c.json({ error: "invalid_body", details: parsed.error.flatten() }, 400);
  const body = parsed.data;

  const touchesBudget =
    body.budgetMicro !== undefined ||
    body.defaultMemberBudgetMicro !== undefined ||
    body.budgetEnforcement !== undefined;
  if (touchesBudget) {
    const notManager = requireOrgManager(c);
    if (notManager) return notManager;
  }

  const patch: Record<string, unknown> = {};
  if (body.name !== undefined) patch.name = body.name;
  if (body.budgetMicro !== undefined) patch.budgetMicro = body.budgetMicro;
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

// DELETE /:id — remove a team (owner/admin).
teams_.delete("/:id", async (c) => {
  const forbidden = requireOrgManager(c);
  if (forbidden) return forbidden;
  const { orgId } = c.get("member");
  const id = c.req.param("id");
  const [deleted] = await withOrg(orgId, (tx) =>
    tx
      .delete(teams)
      .where(and(eq(teams.id, id), eq(teams.orgId, orgId)))
      .returning({ id: teams.id }),
  );
  if (!deleted) return c.json({ error: "not_found" }, 404);
  return c.json({ ok: true });
});

export { teams_ as teams };
