import { Hono } from "hono";
import { cors } from "hono/cors";
import { serveStatic } from "@hono/node-server/serve-static";
import { env } from "@vortex/core";
import { health } from "./shared/health.js";
import { auth } from "./shared/auth.js";
import { sessionMw, type AppEnv } from "./shared/ctx.js";
import { account } from "./features/account/account.router.js";
import { featureRouters } from "./features/index.js";
import { governanceRouters } from "./features/governance/governance.router.js";
import {
  billingRouters,
  webhookRouters,
} from "./features/billing/billing.router.js";
import { gatewayRouter } from "./v1/index.js";
import { platformRouters } from "./features/platform/platform.router.js";

export function createApp() {
  const app = new Hono<AppEnv>();

  app.use(
    "*",
    cors({
      origin: [env.WEB_ORIGIN, env.PLATFORM_ORIGIN],
      credentials: true,
    }),
  );

  app.route("/health", health);

  // better-auth mounts its own routes under /api/auth/*
  app.on(["POST", "GET"], "/api/auth/*", (c) => auth.handler(c.req.raw));

  // dashboard API (/api/*) — session loaded, then feature routers
  app.use("/api/*", sessionMw);
  app.route("/api", account);
  for (const [path, router] of [
    ...featureRouters,
    ...governanceRouters,
    ...billingRouters,
  ]) {
    app.route(path, router);
  }
  for (const [path, router] of webhookRouters) {
    app.route(path, router);
  }

  // platform super-admin API (/platform/*) — SaaS (multi) mode only
  if (env.TENANCY_MODE === "multi") {
    app.use("/platform/*", sessionMw);
    for (const [path, router] of platformRouters) {
      app.route(path, router);
    }
  }

  // gateway (/v1/*) — own key-auth middleware inside
  app.route("/v1", gatewayRouter);

  // production: serve the built consoles same-origin so auth cookies stay
  // first-party (preesm pattern). Tenant console at /, platform at /admin.
  // Build platform with `--base-href=/admin/` so its assets resolve.
  if (env.NODE_ENV === "production") {
    const webDist = process.env.WEB_DIST ?? "./dist/web/browser";
    const platformDist =
      process.env.PLATFORM_DIST ?? "./dist/platform/browser";

    app.use(
      "/admin/*",
      serveStatic({
        root: platformDist,
        rewriteRequestPath: (p) => p.replace(/^\/admin/, "") || "/",
      }),
    );
    app.get("/admin/*", serveStatic({ path: `${platformDist}/index.html` }));

    app.use("/*", serveStatic({ root: webDist }));
    app.get("*", serveStatic({ path: `${webDist}/index.html` }));
  }

  return app;
}

export type App = ReturnType<typeof createApp>;
