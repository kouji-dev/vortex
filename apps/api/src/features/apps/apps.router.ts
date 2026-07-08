import { Hono } from "hono";
import { z } from "zod";
import { eq, and } from "drizzle-orm";
import { withOrg, appAccess } from "@vortex/db";
import { createAppSchema, appPrincipalSchema, appRoleSchema } from "@vortex/shared";
import { type AppEnv, requireMember } from "../../shared/ctx.js";
import { listAccessibleApps, createApp, getApp, canManageApp } from "./apps.service.js";
import { CapExceededError } from "../../shared/caps.js";

const grantSchema = z.object({
  principalType: appPrincipalSchema,
  principalId: z.string(),
  role: appRoleSchema.optional(),
});

export const apps_ = new Hono<AppEnv>();
apps_.use("*", requireMember);

// GET / — apps the caller can access.
apps_.get("/", async (c) => {
  const rows = await listAccessibleApps(c.get("member"));
  return c.json(rows);
});

// POST / — create a service or personal app.
apps_.post("/", async (c) => {
  const body = createAppSchema.parse(await c.req.json());
  try {
    const app = await createApp(c.get("member"), body);
    return c.json(app, 201);
  } catch (e) {
    if (e instanceof CapExceededError)
      return c.json({ error: "plan_limit", cap: e.cap, message: e.message }, 403);
    throw e;
  }
});

// GET /:id — single app.
apps_.get("/:id", async (c) => {
  const { orgId } = c.get("member");
  const app = await getApp(orgId, c.req.param("id"));
  if (!app) return c.json({ error: "not_found" }, 404);
  return c.json(app);
});

// POST /:id/access — grant a team or member access (org owner/admin, or app owner/app_admin).
apps_.post("/:id/access", async (c) => {
  const member = c.get("member");
  const appId = c.req.param("id");
  if (!(await canManageApp(member, appId)))
    return c.json({ error: "forbidden" }, 403);
  const { orgId } = member;
  const body = grantSchema.parse(await c.req.json());

  const app = await getApp(orgId, appId);
  if (!app) return c.json({ error: "not_found" }, 404);

  const [grant] = await withOrg(orgId, (tx) =>
    tx
      .insert(appAccess)
      .values({
        orgId,
        appId,
        principalType: body.principalType,
        principalId: body.principalId,
        role: body.role ?? "app_member",
      })
      .returning(),
  );
  return c.json(grant, 201);
});

// DELETE /:id/access/:grantId — revoke a grant (org owner/admin, or app owner/app_admin).
apps_.delete("/:id/access/:grantId", async (c) => {
  const member = c.get("member");
  const appId = c.req.param("id");
  if (!(await canManageApp(member, appId)))
    return c.json({ error: "forbidden" }, 403);
  const { orgId } = member;
  const grantId = c.req.param("grantId");

  const [deleted] = await withOrg(orgId, (tx) =>
    tx
      .delete(appAccess)
      .where(
        and(
          eq(appAccess.id, grantId),
          eq(appAccess.appId, appId),
          eq(appAccess.orgId, orgId),
        ),
      )
      .returning({ id: appAccess.id }),
  );
  if (!deleted) return c.json({ error: "not_found" }, 404);
  return c.json({ ok: true });
});

export { apps_ as apps };
