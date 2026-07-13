import { Hono } from "hono";
import { z } from "zod";
import { eq, and } from "drizzle-orm";
import { withOrg, appAccess } from "@vortex/db";
import { createAppSchema, appPrincipalSchema, appRoleSchema } from "@vortex/shared";
import { type AppEnv, requireMember } from "../../shared/ctx.js";
import { listAccessibleApps, createApp, getApp, canManageApp } from "./apps.service.js";
import { CapExceededError } from "../../shared/caps.js";
import {
  requireOrgManager,
  assertMemberInOrg,
  assertTeamInOrg,
} from "../../shared/rbac.js";
import { isUniqueViolation } from "../../shared/pg.js";
import { parsePage, pageEnvelope } from "../../shared/pagination.js";

const grantSchema = z.object({
  principalType: appPrincipalSchema,
  principalId: z.string(),
  role: appRoleSchema.optional(),
});

export const apps_ = new Hono<AppEnv>();
apps_.use("*", requireMember);

// GET / — apps the caller can access.
apps_.get("/", async (c) => {
  const page = parsePage(c);
  const rows = await listAccessibleApps(c.get("member"), page);
  return c.json(pageEnvelope(rows, page));
});

// POST / — create a service or personal app.
apps_.post("/", async (c) => {
  const parsed = createAppSchema.safeParse(await c.req.json().catch(() => ({})));
  if (!parsed.success)
    return c.json({ error: "invalid_body", details: parsed.error.flatten() }, 400);
  const body = parsed.data;
  const member = c.get("member");

  // System apps are org infrastructure — owner/admin only.
  if (body.kind === "system") {
    const forbidden = requireOrgManager(c);
    if (forbidden) return forbidden;
  }

  // Creating an app owned by someone else is a management action.
  if (
    body.kind === "personal" &&
    body.ownerMemberId &&
    body.ownerMemberId !== member.membershipId
  ) {
    const forbidden = requireOrgManager(c);
    if (forbidden) return forbidden;
    const target = await withOrg(member.orgId, (tx) =>
      assertMemberInOrg(tx, member.orgId, body.ownerMemberId!),
    );
    if (!target) return c.json({ error: "member_not_in_org" }, 400);
  }

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
  const parsed = grantSchema.safeParse(await c.req.json().catch(() => ({})));
  if (!parsed.success)
    return c.json({ error: "invalid_body", details: parsed.error.flatten() }, 400);
  const body = parsed.data;

  const app = await getApp(orgId, appId);
  if (!app) return c.json({ error: "not_found" }, 404);

  // The principal must live in this org.
  const principalExists = await withOrg(orgId, async (tx) => {
    if (body.principalType === "team")
      return !!(await assertTeamInOrg(tx, orgId, body.principalId));
    return !!(await assertMemberInOrg(tx, orgId, body.principalId));
  });
  if (!principalExists) return c.json({ error: "principal_not_in_org" }, 400);

  try {
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
  } catch (e) {
    if (isUniqueViolation(e, "app_access_uq"))
      return c.json({ error: "duplicate_grant" }, 409);
    throw e;
  }
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
