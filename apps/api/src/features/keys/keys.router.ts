import { Hono } from "hono";
import { z } from "zod";
import { eq, and } from "drizzle-orm";
import { withOrg, apiKeys, apiKeyRules } from "@vortex/db";
import { keyRuleTypeSchema } from "@vortex/shared";
import { type AppEnv, requireMember } from "../../shared/ctx.js";
import { generateApiKey } from "./keys.util.js";
import { resolveEntitlements } from "../../shared/entitlements.js";

/**
 * Gate + clamp a requested custom per-key RPM against the org plan.
 * - allowCustomRateLimit flag false → rejected (Pro+ only).
 * - otherwise clamp to the plan RPM ceiling.
 */
async function gateCustomRpm(
  orgId: string,
  requested: number,
): Promise<{ ok: boolean; value?: number; error?: string }> {
  const ent = await resolveEntitlements(orgId);
  if (!ent.flags?.allowCustomRateLimit) {
    return { ok: false, error: "custom_rate_limit_not_allowed" };
  }
  const value = ent.rpm != null ? Math.min(requested, ent.rpm) : requested;
  return { ok: true, value };
}

const createKeySchema = z.object({
  name: z.string().optional(), // accepted; no dedicated column — informational only
  ownerMemberId: z.string().optional(), // defaults to the caller
  rules: z
    .array(z.object({ ruleType: keyRuleTypeSchema, ruleValue: z.unknown() }))
    .optional(),
  rateLimitRpm: z.number().int().positive().optional(),
  expiresAt: z.string().optional(), // ISO-8601
});

export const keys = new Hono<AppEnv>();
keys.use("*", requireMember);

// GET / — the caller's own keys, masked (never the hash).
keys.get("/", async (c) => {
  const { orgId, membershipId } = c.get("member");
  const rows = await withOrg(orgId, (tx) =>
    tx
      .select({
        id: apiKeys.id,
        keyPrefix: apiKeys.keyPrefix,
        isDefault: apiKeys.isDefault,
        status: apiKeys.status,
        lastUsedAt: apiKeys.lastUsedAt,
      })
      .from(apiKeys)
      .where(eq(apiKeys.ownerMemberId, membershipId)),
  );
  return c.json(rows);
});

// POST / — create a key. Returns the plaintext ONCE.
keys.post("/", async (c) => {
  const { orgId, membershipId } = c.get("member");
  const userId = c.get("user")?.id ?? null;
  const body = createKeySchema.parse(await c.req.json().catch(() => ({})));
  const ownerMemberId = body.ownerMemberId ?? membershipId;
  const gen = generateApiKey();

  let rateLimitRpm: number | null = null;
  if (body.rateLimitRpm != null) {
    const gate = await gateCustomRpm(orgId, body.rateLimitRpm);
    if (!gate.ok) return c.json({ error: "plan_limit", message: gate.error }, 403);
    rateLimitRpm = gate.value ?? null;
  }

  const key = await withOrg(orgId, async (tx) => {
    const [row] = await tx
      .insert(apiKeys)
      .values({
        orgId,
        ownerMemberId,
        keyHash: gen.keyHash,
        keyPrefix: gen.keyPrefix,
        rateLimitRpm,
        expiresAt: body.expiresAt ? new Date(body.expiresAt) : null,
        createdBy: userId,
      })
      .returning();
    if (body.rules?.length) {
      await tx.insert(apiKeyRules).values(
        body.rules.map((r) => ({
          apiKeyId: row!.id,
          ruleType: r.ruleType,
          ruleValue: r.ruleValue,
        })),
      );
    }
    return row!;
  });

  return c.json(
    {
      id: key.id,
      keyPrefix: key.keyPrefix,
      isDefault: key.isDefault,
      status: key.status,
      key: gen.plaintext,
    },
    201,
  );
});

// POST /:id/rotate — revoke the old key, issue a new one. Plaintext ONCE.
keys.post("/:id/rotate", async (c) => {
  const { orgId, membershipId } = c.get("member");
  const userId = c.get("user")?.id ?? null;
  const id = c.req.param("id");
  const gen = generateApiKey();

  const result = await withOrg(orgId, async (tx) => {
    const [old] = await tx
      .select()
      .from(apiKeys)
      .where(
        and(eq(apiKeys.id, id), eq(apiKeys.ownerMemberId, membershipId)),
      )
      .limit(1);
    if (!old) return null;

    await tx
      .update(apiKeys)
      .set({ status: "revoked" })
      .where(eq(apiKeys.id, id));

    const [row] = await tx
      .insert(apiKeys)
      .values({
        orgId,
        ownerMemberId: old.ownerMemberId,
        isDefault: old.isDefault,
        keyHash: gen.keyHash,
        keyPrefix: gen.keyPrefix,
        rateLimitRpm: old.rateLimitRpm,
        expiresAt: old.expiresAt,
        createdBy: userId,
      })
      .returning();
    return row!;
  });

  if (!result) return c.json({ error: "not_found" }, 404);
  return c.json({
    id: result.id,
    keyPrefix: result.keyPrefix,
    isDefault: result.isDefault,
    status: result.status,
    key: gen.plaintext,
  });
});

// PATCH /:id — update a key's custom RPM (Pro+; clamped to plan ceiling).
keys.patch("/:id", async (c) => {
  const { orgId, membershipId } = c.get("member");
  const id = c.req.param("id");
  const body = z
    .object({ rateLimitRpm: z.number().int().positive().nullable() })
    .parse(await c.req.json().catch(() => ({})));

  let rateLimitRpm: number | null = null;
  if (body.rateLimitRpm != null) {
    const gate = await gateCustomRpm(orgId, body.rateLimitRpm);
    if (!gate.ok) return c.json({ error: "plan_limit", message: gate.error }, 403);
    rateLimitRpm = gate.value ?? null;
  }

  const [row] = await withOrg(orgId, (tx) =>
    tx
      .update(apiKeys)
      .set({ rateLimitRpm })
      .where(and(eq(apiKeys.id, id), eq(apiKeys.ownerMemberId, membershipId)))
      .returning({ id: apiKeys.id, rateLimitRpm: apiKeys.rateLimitRpm }),
  );
  if (!row) return c.json({ error: "not_found" }, 404);
  return c.json({ ok: true, id: row.id, rateLimitRpm: row.rateLimitRpm });
});

// POST /:id/revoke — disable a key.
keys.post("/:id/revoke", async (c) => {
  const { orgId, membershipId } = c.get("member");
  const id = c.req.param("id");
  const [row] = await withOrg(orgId, (tx) =>
    tx
      .update(apiKeys)
      .set({ status: "revoked" })
      .where(and(eq(apiKeys.id, id), eq(apiKeys.ownerMemberId, membershipId)))
      .returning({ id: apiKeys.id, status: apiKeys.status }),
  );
  if (!row) return c.json({ error: "not_found" }, 404);
  return c.json({ ok: true, id: row.id, status: row.status });
});
