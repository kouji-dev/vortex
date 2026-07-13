import { Hono } from "hono";
import { z } from "zod";
import { desc, eq, and } from "drizzle-orm";
import { withOrg, teams, memberships, auditLogs } from "@vortex/db";
import { budgetEnforcementSchema } from "@vortex/shared";
import { requireMember, type AppEnv } from "../../shared/ctx.js";
import { requireOrgManager } from "../../shared/rbac.js";
import { redis, budgetKey } from "@vortex/core";
import { reconcileMonth } from "./budget.service.js";
import { appendAudit } from "./audit.service.js";

const teamBudgetSchema = z.object({
  budgetMicro: z.number().int().nonnegative().nullish(),
  defaultMemberBudgetMicro: z.number().int().nonnegative().nullish(),
  enforcement: budgetEnforcementSchema.optional(),
});

const memberBudgetSchema = z.object({
  budgetOverrideMicro: z.number().int().nonnegative().nullish(),
});

// ── budgets ──────────────────────────────────────────────────
export const budgets = new Hono<AppEnv>();
budgets.use("*", requireMember);

// team defaults + per-member effective budget & current burn
budgets.get("/", async (c) => {
  const { orgId } = c.get("member");
  const data = await withOrg(orgId, async (tx) => {
    const teamRows = await tx.select().from(teams);
    const memberRows = await tx.select().from(memberships);
    return { teamRows, memberRows };
  });
  // Batch the per-team spend in one Redis MGET (no per-team DB query).
  const month = new Date().toISOString().slice(0, 7);
  const spendKeys = data.teamRows.map((t) =>
    budgetKey(orgId, "team", t.id, month),
  );
  const spents = spendKeys.length ? await redis.mget(...spendKeys) : [];
  const teamList = data.teamRows.map((t, i) => ({
    id: t.id,
    name: t.name,
    budgetMicro: t.budgetMicro,
    defaultMemberBudgetMicro: t.defaultMemberBudgetMicro,
    enforcement: t.budgetEnforcement,
    spentMicro: Number(spents[i]) || 0,
  }));
  return c.json({
    teams: teamList,
    members: data.memberRows.map((m) => ({
      membershipId: m.id,
      teamId: m.teamId,
      type: m.type,
      overrideMicro: m.budgetOverrideMicro,
    })),
  });
});

budgets.patch("/team/:teamId", async (c) => {
  const forbidden = requireOrgManager(c);
  if (forbidden) return forbidden;
  const m = c.get("member");
  const teamId = c.req.param("teamId");
  const parsed = teamBudgetSchema.safeParse(await c.req.json().catch(() => ({})));
  if (!parsed.success)
    return c.json({ error: "invalid_body", details: parsed.error.flatten() }, 400);
  const body = parsed.data;
  await withOrg(m.orgId, async (tx) => {
    await tx
      .update(teams)
      .set({
        ...(body.budgetMicro !== undefined && { budgetMicro: body.budgetMicro }),
        ...(body.defaultMemberBudgetMicro !== undefined && {
          defaultMemberBudgetMicro: body.defaultMemberBudgetMicro,
        }),
        ...(body.enforcement && { budgetEnforcement: body.enforcement }),
      })
      .where(and(eq(teams.id, teamId), eq(teams.orgId, m.orgId)));
  });
  await appendAudit({
    orgId: m.orgId,
    actor: m.membershipId,
    action: "budget.team.update",
    target: teamId,
    metadata: body,
  });
  return c.json({ ok: true });
});

budgets.patch("/member/:memberId", async (c) => {
  const forbidden = requireOrgManager(c);
  if (forbidden) return forbidden;
  const m = c.get("member");
  const memberId = c.req.param("memberId");
  const parsed = memberBudgetSchema.safeParse(await c.req.json().catch(() => ({})));
  if (!parsed.success)
    return c.json({ error: "invalid_body", details: parsed.error.flatten() }, 400);
  const body = parsed.data;
  await withOrg(m.orgId, async (tx) => {
    await tx
      .update(memberships)
      .set({ budgetOverrideMicro: body.budgetOverrideMicro ?? null })
      .where(and(eq(memberships.id, memberId), eq(memberships.orgId, m.orgId)));
  });
  await appendAudit({
    orgId: m.orgId,
    actor: m.membershipId,
    action: "budget.member.override",
    target: memberId,
    metadata: body,
  });
  return c.json({ ok: true });
});

budgets.post("/reconcile", async (c) => {
  const forbidden = requireOrgManager(c);
  if (forbidden) return forbidden;
  await reconcileMonth(c.get("member").orgId);
  return c.json({ ok: true });
});

// ── audit ────────────────────────────────────────────────────
export const audit = new Hono<AppEnv>();
audit.use("*", requireMember);

audit.get("/", async (c) => {
  const forbidden = requireOrgManager(c);
  if (forbidden) return forbidden;
  const m = c.get("member");
  const rows = await withOrg(m.orgId, (tx) =>
    tx
      .select()
      .from(auditLogs)
      .where(eq(auditLogs.orgId, m.orgId))
      .orderBy(desc(auditLogs.createdAt))
      .limit(200),
  );
  return c.json({ entries: rows });
});

export const governanceRouters: Array<[string, Hono<AppEnv>]> = [
  ["/api/budgets", budgets],
  ["/api/audit", audit],
];
