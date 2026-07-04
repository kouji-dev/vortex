import type { Hono } from "hono";
import type { AppEnv } from "../shared/ctx.js";
import { teams } from "./teams/teams.router.js";
import { members } from "./members/members.router.js";
import { apps } from "./apps/apps.router.js";
import { keys } from "./keys/keys.router.js";
import { providers } from "./providers/providers.router.js";

/** Dashboard feature routers, mounted under /api by app.ts. */
export const featureRouters: Array<[string, Hono<AppEnv>]> = [
  ["/api/teams", teams],
  ["/api/members", members],
  ["/api/apps", apps],
  ["/api/keys", keys],
  ["/api/providers", providers],
];
