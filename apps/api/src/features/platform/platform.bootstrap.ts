import { eq } from "drizzle-orm";
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
    for (const email of configuredAdminEmails) {
      const [user] = await tx
        .select()
        .from(users)
        .where(eq(users.email, email))
        .limit(1);
      if (!user) continue;
      const [existing] = await tx
        .select()
        .from(platformAdmins)
        .where(eq(platformAdmins.userId, user.id))
        .limit(1);
      if (!existing) {
        await tx
          .insert(platformAdmins)
          .values({ userId: user.id, role: "platform_admin" });
      }
    }
  });

  console.log(
    `✓ platform admin email(s): ${configuredAdminEmails.join(", ")} (promoted on sign-in)`,
  );
}
