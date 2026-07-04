import { serve } from "@hono/node-server";
import { env } from "@vortex/core";
import { createApp } from "./app.js";
import { ensureSingleOrg } from "./features/provisioning/provisioning.service.js";
import { ensurePlatformAdmin } from "./features/platform/platform.bootstrap.js";

if (env.TENANCY_MODE === "single") {
  await ensureSingleOrg();
  console.log("✓ single-tenant org ready");
} else {
  // SaaS: seed the first platform admin from config so the platform console
  // is reachable (the create-admin API requires an existing admin).
  await ensurePlatformAdmin();
}

const app = createApp();

// prefer the platform-provided PORT (e.g. Render), else the configured API_PORT
const port = Number(process.env.PORT) || env.API_PORT;

serve({ fetch: app.fetch, port }, (info) => {
  console.log(
    `▲ Vortex API — http://localhost:${info.port}  (tenancy: ${env.TENANCY_MODE})`,
  );
});
