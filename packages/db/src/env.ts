import { config } from "dotenv";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

// load the single repo-root .env regardless of cwd
const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../../..");
config({ path: resolve(root, ".env") });

export const ROOT = root;
export const ADMIN_DATABASE_URL =
  process.env.DATABASE_URL ?? "postgres://vortex:vortex@localhost:5433/vortex";
