import { Hono } from "hono";
import { z } from "zod";
import { requireAuth, type AppEnv } from "../../shared/ctx.js";
import {
  getMembership,
  provisionUser,
} from "../provisioning/provisioning.service.js";
import { CapExceededError } from "../../shared/caps.js";
import { isUniqueViolation } from "../../shared/pg.js";

const provisionSchema = z.object({
  orgName: z.string().min(1).max(100).optional(),
});

export const account = new Hono<AppEnv>();

// Current user + membership (auth required → 401 when signed out). `member` may
// still be null for an authed-but-unprovisioned user (needsProvision: true).
account.get("/me", requireAuth, async (c) => {
  const user = c.get("user")!;
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
  const parsed = provisionSchema.safeParse(await c.req.json().catch(() => ({})));
  if (!parsed.success)
    return c.json({ error: "invalid_body", details: parsed.error.flatten() }, 400);
  try {
    const { ctx, defaultKey } = await provisionUser(user.id, {
      orgName: parsed.data.orgName,
    });
    return c.json({ member: ctx, defaultKey, alreadyProvisioned: false });
  } catch (e) {
    if (e instanceof CapExceededError)
      return c.json({ error: "plan_limit", cap: e.cap, message: e.message }, 403);
    // Concurrent double-provision: another request won the race. Idempotent —
    // return the membership it created.
    if (isUniqueViolation(e, "memberships_org_user_uq")) {
      const member = await getMembership(user.id);
      if (member)
        return c.json({ member, defaultKey: null, alreadyProvisioned: true });
    }
    throw e;
  }
});
