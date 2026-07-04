import { Hono } from "hono";
import { z } from "zod";
import { eq, and } from "drizzle-orm";
import { withOrg, providerCredentials } from "@vortex/db";
import { encryptForOrg } from "@vortex/core";
import { credScopeSchema, priceOverrideSchema } from "@vortex/shared";
import { type AppEnv, requireMember } from "../../shared/ctx.js";
import { requireRole } from "../../shared/rbac.js";

const createCredSchema = z.object({
  provider: z.string().min(1),
  scopeType: credScopeSchema,
  scopeId: z.string().optional(), // app.id when scope=app
  apiKey: z.string().min(1), // plaintext — encrypted server-side, never returned
  label: z.string().optional(),
  region: z.string().optional(),
  priceOverride: priceOverrideSchema.optional(),
  // deployment options: azure {azureResource,azureApiVersion,deployment},
  // vertex {project,region,tokenType}, bedrock {region}
  options: z.record(z.string(), z.unknown()).optional(),
});

const rotateCredSchema = z.object({ apiKey: z.string().min(1) });
const updateCredSchema = z.object({ enabled: z.boolean() });

export const providers = new Hono<AppEnv>();
providers.use("*", requireMember);

// GET / — masked credential list (never the encrypted key).
providers.get("/", async (c) => {
  const { orgId } = c.get("member");
  const rows = await withOrg(orgId, (tx) =>
    tx
      .select({
        id: providerCredentials.id,
        provider: providerCredentials.provider,
        scopeType: providerCredentials.scopeType,
        healthStatus: providerCredentials.healthStatus,
        enabled: providerCredentials.enabled,
      })
      .from(providerCredentials),
  );
  return c.json(rows);
});

// POST / — store a provider credential, encrypting the plaintext key (owner/admin).
providers.post("/", async (c) => {
  const forbidden = requireRole(c, ["owner", "admin"]);
  if (forbidden) return forbidden;
  const { orgId } = c.get("member");
  const body = createCredSchema.parse(await c.req.json());
  const encryptedKey = encryptForOrg(orgId, body.apiKey);

  const [cred] = await withOrg(orgId, (tx) =>
    tx
      .insert(providerCredentials)
      .values({
        orgId,
        provider: body.provider,
        scopeType: body.scopeType,
        scopeId: body.scopeId ?? null,
        label: body.label ?? null,
        region: body.region ?? null,
        options: body.options ?? null,
        encryptedKey,
        priceOverride: body.priceOverride ?? null,
      })
      .returning(),
  );
  return c.json(maskCred(cred!), 201);
});

// POST /:id/rotate — replace the stored key (owner/admin).
providers.post("/:id/rotate", async (c) => {
  const forbidden = requireRole(c, ["owner", "admin"]);
  if (forbidden) return forbidden;
  const { orgId } = c.get("member");
  const id = c.req.param("id");
  const body = rotateCredSchema.parse(await c.req.json());
  const encryptedKey = encryptForOrg(orgId, body.apiKey);

  const [cred] = await withOrg(orgId, (tx) =>
    tx
      .update(providerCredentials)
      .set({ encryptedKey, rotatedAt: new Date(), healthStatus: "valid" })
      .where(
        and(
          eq(providerCredentials.id, id),
          eq(providerCredentials.orgId, orgId),
        ),
      )
      .returning(),
  );
  if (!cred) return c.json({ error: "not_found" }, 404);
  return c.json(maskCred(cred));
});

// PATCH /:id — toggle enabled (owner/admin).
providers.patch("/:id", async (c) => {
  const forbidden = requireRole(c, ["owner", "admin"]);
  if (forbidden) return forbidden;
  const { orgId } = c.get("member");
  const id = c.req.param("id");
  const body = updateCredSchema.parse(await c.req.json());

  const [cred] = await withOrg(orgId, (tx) =>
    tx
      .update(providerCredentials)
      .set({ enabled: body.enabled })
      .where(
        and(
          eq(providerCredentials.id, id),
          eq(providerCredentials.orgId, orgId),
        ),
      )
      .returning(),
  );
  if (!cred) return c.json({ error: "not_found" }, 404);
  return c.json(maskCred(cred));
});

// POST /:id/test — health check stub; marks the credential valid (owner/admin).
providers.post("/:id/test", async (c) => {
  const forbidden = requireRole(c, ["owner", "admin"]);
  if (forbidden) return forbidden;
  const { orgId } = c.get("member");
  const id = c.req.param("id");

  const [cred] = await withOrg(orgId, (tx) =>
    tx
      .update(providerCredentials)
      .set({ healthStatus: "valid", lastCheckedAt: new Date() })
      .where(
        and(
          eq(providerCredentials.id, id),
          eq(providerCredentials.orgId, orgId),
        ),
      )
      .returning({ id: providerCredentials.id }),
  );
  if (!cred) return c.json({ error: "not_found" }, 404);
  return c.json({ ok: true });
});

type Cred = typeof providerCredentials.$inferSelect;
function maskCred(cred: Cred) {
  return {
    id: cred.id,
    provider: cred.provider,
    scopeType: cred.scopeType,
    scopeId: cred.scopeId,
    healthStatus: cred.healthStatus,
    enabled: cred.enabled,
  };
}
