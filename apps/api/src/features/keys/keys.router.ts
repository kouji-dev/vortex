import { Hono, type Context } from "hono";
import { z } from "zod";
import { eq, and, type SQL } from "drizzle-orm";
import { withOrg, apiKeys, apiKeyRules } from "@vortex/db";
import { type AppEnv, requireMember } from "../../shared/ctx.js";
import { generateApiKey } from "./keys.util.js";
import { resolveEntitlements } from "../../shared/entitlements.js";
import {
  isOrgManager,
  requireOrgManager,
  assertMemberInOrg,
} from "../../shared/rbac.js";
import { parsePage, pageEnvelope } from "../../shared/pagination.js";

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

// IPv4 CIDR: dotted quad (each octet 0-255) + /0-32 prefix.
const CIDR_RE =
  /^((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\/(3[0-2]|[12]?\d)$/;

const nameList = z.array(z.string().min(1)).min(1);

const keyRuleSchema = z.discriminatedUnion("ruleType", [
  z.object({ ruleType: z.literal("allow_models"), ruleValue: nameList }),
  z.object({ ruleType: z.literal("deny_models"), ruleValue: nameList }),
  z.object({ ruleType: z.literal("allow_providers"), ruleValue: nameList }),
  z.object({ ruleType: z.literal("deny_providers"), ruleValue: nameList }),
  z.object({
    ruleType: z.literal("ip_cidrs"),
    ruleValue: z
      .array(z.string().regex(CIDR_RE, "invalid CIDR (expected a.b.c.d/nn)"))
      .min(1),
  }),
]);

const createKeySchema = z.object({
  name: z.string().optional(), // accepted; no dedicated column — informational only
  ownerMemberId: z.string().optional(), // defaults to the caller
  rules: z.array(keyRuleSchema).optional(),
  rateLimitRpm: z.number().int().positive().optional(),
  expiresAt: z
    .string()
    .datetime({ offset: true })
    .refine((v) => new Date(v).getTime() > Date.now(), {
      message: "expiresAt must be in the future",
    })
    .optional(),
});

export const keys = new Hono<AppEnv>();
keys.use("*", requireMember);

// GET / — the caller's own keys, masked (never the hash). Org owner/admin may
// list every key, or filter to one member with `?memberId=`.
keys.get("/", async (c) => {
  const member = c.get("member");
  const { orgId, membershipId } = member;
  const page = parsePage(c);
  const memberId = c.req.query("memberId");

  let ownerFilter: SQL | undefined;
  if (isOrgManager(member)) {
    ownerFilter = memberId ? eq(apiKeys.ownerMemberId, memberId) : undefined;
  } else {
    // Plain members only ever see their own keys.
    if (memberId && memberId !== membershipId)
      return c.json({ error: "forbidden" }, 403);
    ownerFilter = eq(apiKeys.ownerMemberId, membershipId);
  }

  const rows = await withOrg(orgId, (tx) =>
    tx
      .select({
        id: apiKeys.id,
        keyPrefix: apiKeys.keyPrefix,
        ownerMemberId: apiKeys.ownerMemberId,
        isDefault: apiKeys.isDefault,
        status: apiKeys.status,
        lastUsedAt: apiKeys.lastUsedAt,
      })
      .from(apiKeys)
      .where(and(eq(apiKeys.orgId, orgId), ownerFilter))
      .limit(page.limit)
      .offset(page.offset),
  );
  return c.json(pageEnvelope(rows, page));
});

// POST / — create a key. Returns the plaintext ONCE.
keys.post("/", async (c) => {
  const { orgId, membershipId } = c.get("member");
  const userId = c.get("user")?.id ?? null;
  const parsed = createKeySchema.safeParse(await c.req.json().catch(() => ({})));
  if (!parsed.success)
    return c.json({ error: "invalid_body", details: parsed.error.flatten() }, 400);
  const body = parsed.data;
  const ownerMemberId = body.ownerMemberId ?? membershipId;

  // Minting a key for someone else is a management action.
  if (ownerMemberId !== membershipId) {
    const forbidden = requireOrgManager(c);
    if (forbidden) return forbidden;
    const target = await withOrg(orgId, (tx) =>
      assertMemberInOrg(tx, orgId, ownerMemberId),
    );
    if (!target) return c.json({ error: "member_not_in_org" }, 400);
  }

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

/** Org + ownership scope for key mutations: managers may touch any org key. */
function keyScope(c: Context<AppEnv>, id: string): SQL | undefined {
  const member = c.get("member");
  return and(
    eq(apiKeys.id, id),
    eq(apiKeys.orgId, member.orgId),
    isOrgManager(member)
      ? undefined
      : eq(apiKeys.ownerMemberId, member.membershipId),
  );
}

// POST /:id/rotate — revoke the old key, issue a new one. Plaintext ONCE.
keys.post("/:id/rotate", async (c) => {
  const { orgId } = c.get("member");
  const userId = c.get("user")?.id ?? null;
  const id = c.req.param("id");
  const gen = generateApiKey();

  const result = await withOrg(orgId, async (tx) => {
    const [old] = await tx
      .select()
      .from(apiKeys)
      .where(keyScope(c, id))
      .limit(1);
    if (!old) return null;

    await tx
      .update(apiKeys)
      .set({ status: "revoked" })
      .where(and(eq(apiKeys.id, id), eq(apiKeys.orgId, orgId)));

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
  const { orgId } = c.get("member");
  const id = c.req.param("id");
  const parsed = z
    .object({ rateLimitRpm: z.number().int().positive().nullable() })
    .safeParse(await c.req.json().catch(() => ({})));
  if (!parsed.success)
    return c.json({ error: "invalid_body", details: parsed.error.flatten() }, 400);
  const body = parsed.data;

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
      .where(keyScope(c, id))
      .returning({ id: apiKeys.id, rateLimitRpm: apiKeys.rateLimitRpm }),
  );
  if (!row) return c.json({ error: "not_found" }, 404);
  return c.json({ ok: true, id: row.id, rateLimitRpm: row.rateLimitRpm });
});

// POST /:id/revoke — disable a key.
keys.post("/:id/revoke", async (c) => {
  const { orgId } = c.get("member");
  const id = c.req.param("id");
  const [row] = await withOrg(orgId, (tx) =>
    tx
      .update(apiKeys)
      .set({ status: "revoked" })
      .where(keyScope(c, id))
      .returning({ id: apiKeys.id, status: apiKeys.status }),
  );
  if (!row) return c.json({ error: "not_found" }, 404);
  return c.json({ ok: true, id: row.id, status: row.status });
});
