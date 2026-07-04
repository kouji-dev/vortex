import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { db, users, sessions, accounts, verifications } from "@vortex/db";
import { env } from "@vortex/core";

// Enable a social provider only when both id + secret are configured.
const socialProviders = {
  ...(env.GITHUB_CLIENT_ID && env.GITHUB_CLIENT_SECRET
    ? {
        github: {
          clientId: env.GITHUB_CLIENT_ID,
          clientSecret: env.GITHUB_CLIENT_SECRET,
        },
      }
    : {}),
  ...(env.GOOGLE_CLIENT_ID && env.GOOGLE_CLIENT_SECRET
    ? {
        google: {
          clientId: env.GOOGLE_CLIENT_ID,
          clientSecret: env.GOOGLE_CLIENT_SECRET,
        },
      }
    : {}),
};

export const auth = betterAuth({
  secret: env.BETTER_AUTH_SECRET,
  baseURL: env.BETTER_AUTH_URL,
  trustedOrigins: [env.WEB_ORIGIN, env.PLATFORM_ORIGIN],
  emailAndPassword: {
    enabled: true,
    autoSignIn: true,
    // Dev only: no mailer wired up yet — log the reset link so it can be
    // copied from the server console.
    sendResetPassword: async ({ user, url }) => {
      console.log(`🔑 reset ${user.email}: ${url}`);
    },
  },
  socialProviders,
  // Link a social sign-in to an existing account with the same (verified) email,
  // so signing in with GitHub/Google reaches the same user (e.g. the seeded
  // platform admin) instead of creating a duplicate.
  account: {
    accountLinking: {
      enabled: true,
      trustedProviders: ["github", "google"],
    },
  },
  database: drizzleAdapter(db, {
    provider: "pg",
    schema: {
      user: users,
      session: sessions,
      account: accounts,
      verification: verifications,
    },
  }),
});

export type AuthSession = typeof auth.$Infer.Session;
