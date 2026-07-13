import { Hono } from "hono";
import { z } from "zod";
import { eq, and } from "drizzle-orm";
import { withOrg, providerCredentials, apps } from "@vortex/db";
import {
  encryptForOrg,
  decryptForOrg,
  resolveEndpoint,
  type ProviderOptions,
} from "@vortex/core";
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

// ── credential health check ──────────────────────────────────

const CHECK_TIMEOUT_MS = 5_000;
// Providers whose endpoints are deployment-specific (no plain models list):
// probe with a 1-token completion instead.
const DEPLOYMENT_PROVIDERS = new Set(["azure", "bedrock", "vertex"]);
const PROBE_MODEL: Record<string, string> = {
  bedrock: "amazon.nova-micro-v1:0",
  vertex: "gemini-2.0-flash-lite",
};

function probeBody(provider: string): unknown {
  if (provider === "vertex") {
    return {
      contents: [{ role: "user", parts: [{ text: "ping" }] }],
      generationConfig: { maxOutputTokens: 1 },
    };
  }
  // azure / bedrock speak the OpenAI chat format
  return {
    ...(provider === "bedrock" ? { model: PROBE_MODEL.bedrock } : {}),
    messages: [{ role: "user", content: "ping" }],
    max_tokens: 1,
  };
}

/**
 * Live-check a credential: decrypt the key and hit the provider.
 * - standard providers: GET the models endpoint.
 * - azure/bedrock/vertex: 1-token completion (deployment-specific endpoints).
 * 401/403, network failure, or timeout (5s) → "invalid".
 */
async function checkCredential(
  orgId: string,
  cred: {
    provider: string;
    encryptedKey: string;
    options: unknown;
    region: string | null;
  },
): Promise<"valid" | "invalid"> {
  let token: string;
  try {
    token = decryptForOrg(orgId, cred.encryptedKey);
  } catch {
    return "invalid";
  }
  const options = {
    ...((cred.options as ProviderOptions | null) ?? {}),
    ...(cred.region ? { region: cred.region } : {}),
  } as ProviderOptions;
  const deployment = DEPLOYMENT_PROVIDERS.has(cred.provider);

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), CHECK_TIMEOUT_MS);
  try {
    let resp: Response;
    if (deployment) {
      const { url, headers } = resolveEndpoint(cred.provider, {
        token,
        model: PROBE_MODEL[cred.provider] ?? "probe",
        capability: "chat",
        stream: false,
        options,
      });
      resp = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(probeBody(cred.provider)),
        signal: ctrl.signal,
      });
    } else {
      const { url, headers } = resolveEndpoint(cred.provider, {
        token,
        model: "",
        capability: "models",
        stream: false,
        options,
      });
      resp = await fetch(url, { method: "GET", headers, signal: ctrl.signal });
    }
    void resp.body?.cancel().catch(() => {});
    if (resp.status === 401 || resp.status === 403) return "invalid";
    if (resp.ok) return "valid";
    // Deployment probes may 400/404 on the probe model while the key itself is
    // fine — count any authenticated (non-401/403) 4xx as a working key.
    if (deployment && resp.status < 500) return "valid";
    return "invalid";
  } catch {
    return "invalid"; // network error / timeout / unresolvable endpoint
  } finally {
    clearTimeout(timer);
  }
}

async function recordHealth(
  orgId: string,
  credId: string,
  healthStatus: "valid" | "invalid",
): Promise<void> {
  await withOrg(orgId, (tx) =>
    tx
      .update(providerCredentials)
      .set({ healthStatus, lastCheckedAt: new Date() })
      .where(
        and(
          eq(providerCredentials.id, credId),
          eq(providerCredentials.orgId, orgId),
        ),
      ),
  );
}

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

  // app-scoped credential → scopeId must be one of this org's apps.
  if (body.scopeType === "app") {
    if (!body.scopeId) {
      return c.json(
        { error: "invalid_scope", message: "scopeId is required for app scope" },
        400,
      );
    }
    const [app] = await withOrg(orgId, (tx) =>
      tx
        .select({ id: apps.id })
        .from(apps)
        .where(and(eq(apps.id, body.scopeId!), eq(apps.orgId, orgId)))
        .limit(1),
    );
    if (!app) {
      return c.json(
        { error: "invalid_scope", message: "scopeId is not an app of this org" },
        400,
      );
    }
  }

  const encryptedKey = encryptForOrg(orgId, body.apiKey);
  const [cred] = await withOrg(orgId, (tx) =>
    tx
      .insert(providerCredentials)
      .values({
        orgId,
        provider: body.provider,
        scopeType: body.scopeType,
        scopeId: body.scopeType === "app" ? body.scopeId! : null,
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

// POST /:id/rotate — replace the stored key, then live-check it (owner/admin).
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
      .set({ encryptedKey, rotatedAt: new Date() })
      .where(
        and(
          eq(providerCredentials.id, id),
          eq(providerCredentials.orgId, orgId),
        ),
      )
      .returning(),
  );
  if (!cred) return c.json({ error: "not_found" }, 404);

  const healthStatus = await checkCredential(orgId, cred);
  await recordHealth(orgId, cred.id, healthStatus);
  return c.json(maskCred({ ...cred, healthStatus }));
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

// POST /:id/test — live credential check against the provider (owner/admin).
providers.post("/:id/test", async (c) => {
  const forbidden = requireRole(c, ["owner", "admin"]);
  if (forbidden) return forbidden;
  const { orgId } = c.get("member");
  const id = c.req.param("id");

  const [cred] = await withOrg(orgId, (tx) =>
    tx
      .select()
      .from(providerCredentials)
      .where(
        and(
          eq(providerCredentials.id, id),
          eq(providerCredentials.orgId, orgId),
        ),
      )
      .limit(1),
  );
  if (!cred) return c.json({ error: "not_found" }, 404);

  const healthStatus = await checkCredential(orgId, cred);
  await recordHealth(orgId, cred.id, healthStatus);
  return c.json({ ok: healthStatus === "valid", healthStatus });
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
