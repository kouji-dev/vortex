import { inArray } from "drizzle-orm";
import { withBypass, users, platformAdmins } from "@vortex/db";
import { env } from "@vortex/core";

const configuredAdminEmails = (env.PLATFORM_ADMIN_EMAIL ?? "")
  .split(",")
  .map((e) => e.trim().toLowerCase())
  .filter(Boolean);

/**
 * Bootstrap platform admins (SaaS / multi mode) from config.
 *
 * We intentionally do NOT pre-create a password account for the configured
 * emails: a pre-existing account would collide with a later social sign-in for
 * the same email (better-auth throws `account_not_linked`). Instead:
 *   • here — promote any user that ALREADY exists with a configured email;
 *   • on first `/platform/*` access — `requirePlatformAdmin` promotes a user
 *     whose email matches (covers fresh social/GitHub/Google sign-ins).
 * Idempotent — safe on every boot.
 */
export async function ensurePlatformAdmin(): Promise<void> {
  if (!configuredAdminEmails.length) return;

  await withBypass(async (tx) => {
    // 1 read: users that actually exist for the configured emails.
    const matched = await tx
      .select({ id: users.id })
      .from(users)
      .where(inArray(users.email, configuredAdminEmails));
    if (!matched.length) return;

    // 1 read: which of them are already platform admins.
    const userIds = matched.map((u) => u.id);
    const existing = await tx
      .select({ userId: platformAdmins.userId })
      .from(platformAdmins)
      .where(inArray(platformAdmins.userId, userIds));
    const already = new Set(existing.map((e) => e.userId));

    // 1 bulk insert for the remainder.
    const toInsert = userIds
      .filter((id) => !already.has(id))
      .map((userId) => ({ userId, role: "platform_admin" as const }));
    if (toInsert.length) await tx.insert(platformAdmins).values(toInsert);
  });

  console.log(
    `✓ platform admin email(s): ${configuredAdminEmails.join(", ")} (promoted on sign-in)`,
  );
}
