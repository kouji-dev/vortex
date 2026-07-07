import { Hono } from "hono";
import { desc, eq } from "drizzle-orm";
import { withOrg, teams, memberships, auditLogs } from "@vortex/db";
import { requireMember, type AppEnv } from "../../shared/ctx.js";
import { poolSpend, reconcileMonth } from "./budget.service.js";
import { appendAudit } from "./audit.service.js";

function isAdmin(role: string): boolean {
  return role === "owner" || role === "admin";
}

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
  const teamList = await Promise.all(
    data.teamRows.map(async (t) => ({
      id: t.id,
      name: t.name,
      budgetMicro: t.budgetMicro,
      defaultMemberBudgetMicro: t.defaultMemberBudgetMicro,
      enforcement: t.budgetEnforcement,
      spentMicro: await poolSpend(orgId, t.id),
    })),
  );
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
  const m = c.get("member");
  if (!isAdmin(m.role)) return c.json({ error: "forbidden" }, 403);
  const teamId = c.req.param("teamId");
  const body = (await c.req.json().catch(() => ({}))) as {
    budgetMicro?: number | null;
    defaultMemberBudgetMicro?: number | null;
    enforcement?: "hard" | "soft";
  };
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
      .where(eq(teams.id, teamId));
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
  const m = c.get("member");
  if (!isAdmin(m.role)) return c.json({ error: "forbidden" }, 403);
  const memberId = c.req.param("memberId");
  const body = (await c.req.json().catch(() => ({}))) as {
    budgetOverrideMicro?: number | null;
  };
  await withOrg(m.orgId, async (tx) => {
    await tx
      .update(memberships)
      .set({ budgetOverrideMicro: body.budgetOverrideMicro ?? null })
      .where(eq(memberships.id, memberId));
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
  const m = c.get("member");
  if (!isAdmin(m.role)) return c.json({ error: "forbidden" }, 403);
  await reconcileMonth(m.orgId);
  return c.json({ ok: true });
});

// ── audit ────────────────────────────────────────────────────
export const audit = new Hono<AppEnv>();
audit.use("*", requireMember);

audit.get("/", async (c) => {
  const m = c.get("member");
  if (!isAdmin(m.role)) return c.json({ error: "forbidden" }, 403);
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
