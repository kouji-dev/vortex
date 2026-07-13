import { Hono } from "hono";
import { createMiddleware } from "hono/factory";
import { desc, eq, sql } from "drizzle-orm";
import {
  withBypass,
  organizations,
  memberships,
  apps,
  usageRecords,
  plans,
  platformAdmins,
  platformAuditLogs,
  users,
} from "@vortex/db";
import { z } from "zod";
import { env } from "@vortex/core";
import { platformRoleSchema } from "@vortex/shared";
import { type AppEnv } from "../../shared/ctx.js";
import { requirePlatformRole } from "../../shared/rbac.js";
import { isUniqueViolation } from "../../shared/pg.js";
import { createTenantOrg } from "../provisioning/provisioning.service.js";
import { hashChainedInsert } from "../governance/audit.service.js";

const configuredAdminEmails = (env.PLATFORM_ADMIN_EMAIL ?? "")
  .split(",")
  .map((e) => e.trim().toLowerCase())
  .filter(Boolean);

/** Vendor super-admin only (SaaS). Requires the user to be a platform_admin. */
export const requirePlatformAdmin = createMiddleware<AppEnv>(async (c, next) => {
  const user = c.get("user");
  if (!user) return c.json({ error: "unauthorized" }, 401);
  const role = await withBypass(async (tx) => {
    const [pa] = await tx
      .select()
      .from(platformAdmins)
      .where(eq(platformAdmins.userId, user.id))
      .limit(1);
    if (pa) return pa.role;
    // Auto-promote: a signed-in user whose email matches a configured platform
    // admin becomes one. This is what lets social sign-in (GitHub/Google) with
    // the superadmin email reach the platform console.
    if (configuredAdminEmails.includes(user.email.toLowerCase())) {
      await tx
        .insert(platformAdmins)
        .values({ userId: user.id, role: "platform_admin" })
        .onConflictDoNothing();
      return "platform_admin" as const;
    }
    return null;
  });
  if (!role) return c.json({ error: "forbidden" }, 403);
  c.set("platformRole", role);
  await next();
});

async function auditPlatform(
  userId: string,
  action: string,
  targetOrg?: string,
  metadata: Record<string, unknown> = {},
) {
  await withBypass(async (tx) => {
    await hashChainedInsert(tx, {
      lockKey: "audit:platform",
      payload: { action, targetOrg, metadata },
      getPrev: async () => {
        const [last] = await tx
          .select({ h: platformAuditLogs.entryHash })
          .from(platformAuditLogs)
          .orderBy(desc(platformAuditLogs.createdAt), desc(platformAuditLogs.id))
          .limit(1);
        return last?.h ?? null;
      },
      insert: async (prevHash, entryHash) => {
        const [pa] = await tx
          .select()
          .from(platformAdmins)
          .where(eq(platformAdmins.userId, userId))
          .limit(1);
        await tx.insert(platformAuditLogs).values({
          platformAdminId: pa?.id ?? null,
          action,
          targetOrg: targetOrg ?? null,
          metadata,
          prevHash,
          entryHash,
        });
      },
    });
  });
}

export const platform = new Hono<AppEnv>();
platform.use("*", requirePlatformAdmin);

// ── tenants ──────────────────────────────────────────────────
platform.get("/tenants", async (c) => {
  const rows = await withBypass(async (tx) => {
    const orgs = await tx.select().from(organizations);
    return Promise.all(
      orgs.map(async (o) => {
        const [mc] = await tx
          .select({ n: sql<number>`count(*)::int` })
          .from(memberships)
          .where(eq(memberships.orgId, o.id));
        const [ac] = await tx
          .select({ n: sql<number>`count(*)::int` })
          .from(apps)
          .where(eq(apps.orgId, o.id));
        const [sp] = await tx
          .select({ s: sql<number>`coalesce(sum(${usageRecords.costMicro}),0)::bigint` })
          .from(usageRecords)
          .where(eq(usageRecords.orgId, o.id));
        return {
          id: o.id,
          name: o.name,
          status: o.status,
          planId: o.planId,
          createdAt: o.createdAt,
          members: mc?.n ?? 0,
          apps: ac?.n ?? 0,
          spendMicro: Number(sp?.s ?? 0),
        };
      }),
    );
  });
  return c.json({ tenants: rows });
});

platform.post("/tenants", async (c) => {
  const forbidden = requirePlatformRole(c, ["platform_owner", "platform_admin"]);
  if (forbidden) return forbidden;
  const { name } = (await c.req.json().catch(() => ({}))) as { name?: string };
  if (!name) return c.json({ error: "name_required" }, 400);
  const orgId = await createTenantOrg(name);
  await auditPlatform(c.get("user")!.id, "tenant.provision", orgId, { name });
  return c.json({ id: orgId, name });
});

async function setStatus(orgId: string, status: "active" | "suspended") {
  await withBypass((tx) =>
    tx.update(organizations).set({ status }).where(eq(organizations.id, orgId)),
  );
}

platform.post("/tenants/:id/suspend", async (c) => {
  const forbidden = requirePlatformRole(c, ["platform_owner", "platform_admin"]);
  if (forbidden) return forbidden;
  const id = c.req.param("id");
  await setStatus(id, "suspended");
  await auditPlatform(c.get("user")!.id, "tenant.suspend", id);
  return c.json({ ok: true });
});

platform.post("/tenants/:id/reactivate", async (c) => {
  const forbidden = requirePlatformRole(c, ["platform_owner", "platform_admin"]);
  if (forbidden) return forbidden;
  const id = c.req.param("id");
  await setStatus(id, "active");
  await auditPlatform(c.get("user")!.id, "tenant.reactivate", id);
  return c.json({ ok: true });
});

platform.delete("/tenants/:id", async (c) => {
  // Destroying a tenant is irreversible — platform owner only.
  const forbidden = requirePlatformRole(c, ["platform_owner"]);
  if (forbidden) return forbidden;
  const id = c.req.param("id");
  await withBypass((tx) =>
    tx.delete(organizations).where(eq(organizations.id, id)),
  );
  await auditPlatform(c.get("user")!.id, "tenant.delete", id);
  return c.json({ ok: true });
});

// ── cross-tenant usage ───────────────────────────────────────
platform.get("/usage", async (c) => {
  const rows = await withBypass((tx) =>
    tx
      .select({
        orgId: usageRecords.orgId,
        provider: usageRecords.provider,
        model: usageRecords.model,
        requests: sql<number>`count(*)::int`,
        totalTokens: sql<number>`coalesce(sum(${usageRecords.totalTokens}),0)::int`,
        costMicro: sql<number>`coalesce(sum(${usageRecords.costMicro}),0)::bigint`,
      })
      .from(usageRecords)
      .groupBy(usageRecords.orgId, usageRecords.provider, usageRecords.model),
  );
  return c.json({
    rows: rows.map((r) => ({ ...r, costMicro: Number(r.costMicro) })),
  });
});

// ── plans / admins / audit ───────────────────────────────────
platform.get("/plans", async (c) =>
  c.json({ plans: await withBypass((tx) => tx.select().from(plans)) }),
);

const createPlanSchema = z.object({
  name: z.string().min(1).max(100),
  stripePriceId: z.string().optional(),
  priceMicro: z.number().int().nonnegative().optional(),
  limits: z.record(z.unknown()).default({}),
});

platform.post("/plans", async (c) => {
  const forbidden = requirePlatformRole(c, ["platform_owner", "platform_admin"]);
  if (forbidden) return forbidden;
  const parsed = createPlanSchema.safeParse(await c.req.json().catch(() => ({})));
  if (!parsed.success)
    return c.json({ error: "invalid_body", details: parsed.error.flatten() }, 400);
  const b = parsed.data;
  const [p] = await withBypass((tx) =>
    tx
      .insert(plans)
      .values({
        name: b.name,
        stripePriceId: b.stripePriceId,
        priceMicro: b.priceMicro,
        limits: b.limits,
      })
      .returning(),
  );
  return c.json(p);
});

platform.get("/admins", async (c) => {
  const rows = await withBypass((tx) =>
    tx
      .select({
        id: platformAdmins.id,
        role: platformAdmins.role,
        email: users.email,
        name: users.name,
      })
      .from(platformAdmins)
      .leftJoin(users, eq(users.id, platformAdmins.userId)),
  );
  return c.json({ admins: rows });
});

const createAdminSchema = z.object({
  email: z.string().email(),
  role: platformRoleSchema.default("platform_admin"),
});

platform.post("/admins", async (c) => {
  // Granting platform access is owner-only.
  const forbidden = requirePlatformRole(c, ["platform_owner"]);
  if (forbidden) return forbidden;
  const parsed = createAdminSchema.safeParse(await c.req.json().catch(() => ({})));
  if (!parsed.success)
    return c.json({ error: "invalid_body", details: parsed.error.flatten() }, 400);
  const { email, role } = parsed.data;
  try {
    const created = await withBypass(async (tx) => {
      const [u] = await tx
        .select()
        .from(users)
        .where(eq(users.email, email))
        .limit(1);
      if (!u) return null;
      const [pa] = await tx
        .insert(platformAdmins)
        .values({ userId: u.id, role })
        .returning();
      return pa;
    });
    if (!created) return c.json({ error: "user_not_found" }, 404);
    return c.json(created);
  } catch (e) {
    if (isUniqueViolation(e)) return c.json({ error: "already_admin" }, 409);
    throw e;
  }
});

platform.get("/audit", async (c) => {
  const rows = await withBypass((tx) =>
    tx
      .select()
      .from(platformAuditLogs)
      .orderBy(desc(platformAuditLogs.createdAt))
      .limit(200),
  );
  return c.json({ entries: rows });
});

export const platformRouters: Array<[string, Hono<AppEnv>]> = [
  ["/platform", platform],
];
