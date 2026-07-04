import { Hono } from "hono";
import { requireAuth, type AppEnv } from "../../shared/ctx.js";
import {
  getMembership,
  provisionUser,
} from "../provisioning/provisioning.service.js";

export const account = new Hono<AppEnv>();

// Current user + membership (null-safe; tells the client if provisioning is needed).
account.get("/me", async (c) => {
  const user = c.get("user");
  if (!user) return c.json({ user: null, member: null, needsProvision: false });
  const member = await getMembership(user.id);
  return c.json({ user, member, needsProvision: !member });
});

// Provision the signed-up user into an org (idempotent). Returns default key once.
account.post("/provision", requireAuth, async (c) => {
  const user = c.get("user")!;
  const existing = await getMembership(user.id);
  if (existing) {
    return c.json({
      member: existing,
      defaultKey: null,
      alreadyProvisioned: true,
    });
  }
  const body = (await c.req.json().catch(() => ({}))) as { orgName?: string };
  const { ctx, defaultKey } = await provisionUser(user.id, {
    orgName: body.orgName,
  });
  return c.json({ member: ctx, defaultKey, alreadyProvisioned: false });
});
