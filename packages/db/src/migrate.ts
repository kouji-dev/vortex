import { ADMIN_DATABASE_URL } from "./env.js";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import postgres from "postgres";
import { drizzle } from "drizzle-orm/postgres-js";
import { migrate } from "drizzle-orm/postgres-js/migrator";

const here = dirname(fileURLToPath(import.meta.url));
const drizzleDir = resolve(here, "../drizzle");

async function main() {
  // migrations + RLS run as the owner/superuser
  const admin = postgres(ADMIN_DATABASE_URL, { max: 1 });
  const db = drizzle(admin);

  console.log("→ running drizzle migrations…");
  await migrate(db, { migrationsFolder: drizzleDir });

  console.log("→ applying RLS policies…");
  const rls = readFileSync(resolve(drizzleDir, "rls.sql"), "utf8");
  await admin.unsafe(rls);

  await admin.end();
  console.log("✓ migrate complete");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
