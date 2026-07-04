import { eq } from "drizzle-orm";
import {
  withBypass,
  organizations,
  teams,
  memberships,
  apps,
  apiKeys,
  type Tx,
} from "@vortex/db";
import { env } from "@vortex/core";
import { generateApiKey } from "../keys/keys.util.js";

const SINGLE_ORG_NAME = process.env.SEED_ORG_NAME ?? "Acme";
const DEFAULT_TEAM_BUDGET_MICRO = 500_000_000; // $500 / member / month

/** Create a technical member (service account) in a team. */
async function createTechnicalMember(tx: Tx, orgId: string, teamId: string) {
  const [m] = await tx
    .insert(memberships)
    .values({ orgId, type: "technical", teamId, teamRole: "member" })
    .returning();
  return m!;
}

/** Seed the predefined system "Chat" app + its technical member. */
async function seedChatApp(tx: Tx, orgId: string, teamId: string) {
  const tech = await createTechnicalMember(tx, orgId, teamId);
  await tx.insert(apps).values({
    orgId,
    name: "Chat",
    kind: "system",
    technicalMemberId: tech.id,
  });
}

/** Ensure the single-tenant org exists (single mode). Returns its id. */
export async function ensureSingleOrg(): Promise<string> {
  return withBypass(async (tx) => {
    const existing = await tx.select().from(organizations).limit(1);
    if (existing[0]) return existing[0].id;
    const [org] = await tx
      .insert(organizations)
      .values({ name: SINGLE_ORG_NAME })
      .returning();
    const [team] = await tx
      .insert(teams)
      .values({
        orgId: org!.id,
        name: "Default",
        defaultMemberBudgetMicro: DEFAULT_TEAM_BUDGET_MICRO,
        budgetEnforcement: "hard",
      })
      .returning();
    await seedChatApp(tx, org!.id, team!.id);
    return org!.id;
  });
}

/** Platform-created tenant org shell (no owner yet — invited via signup + provision). */
export async function createTenantOrg(name: string): Promise<string> {
  return withBypass(async (tx) => {
    const [org] = await tx.insert(organizations).values({ name }).returning();
    const [team] = await tx
      .insert(teams)
      .values({
        orgId: org!.id,
        name: "Default",
        defaultMemberBudgetMicro: DEFAULT_TEAM_BUDGET_MICRO,
        budgetEnforcement: "hard",
      })
      .returning();
    await seedChatApp(tx, org!.id, team!.id);
    return org!.id;
  });
}

export type MemberContext = {
  membershipId: string;
  orgId: string;
  role: "owner" | "admin" | "member";
  teamId: string | null;
};

/** Look up a user's membership (single org). */
export async function getMembership(
  userId: string,
): Promise<MemberContext | null> {
  return withBypass(async (tx) => {
    const [m] = await tx
      .select()
      .from(memberships)
      .where(eq(memberships.userId, userId))
      .limit(1);
    if (!m) return null;
    return {
      membershipId: m.id,
      orgId: m.orgId,
      role: (m.role ?? "member") as MemberContext["role"],
      teamId: m.teamId,
    };
  });
}

/**
 * Provision a signed-up user into an org.
 * - single mode: attach to the one org (owner if first human, else member)
 * - multi mode: create a new org with them as owner
 * Auto-issues a default member key; returns its one-time plaintext.
 */
export async function provisionUser(
  userId: string,
  opts: { orgName?: string } = {},
): Promise<{ ctx: MemberContext; defaultKey: string }> {
  return withBypass(async (tx) => {
    let orgId: string;
    let defaultTeamId: string;
    let role: "owner" | "admin" | "member";

    if (env.TENANCY_MODE === "multi") {
      const [org] = await tx
        .insert(organizations)
        .values({ name: opts.orgName ?? "My Org" })
        .returning();
      orgId = org!.id;
      const [team] = await tx
        .insert(teams)
        .values({
          orgId,
          name: "Default",
          defaultMemberBudgetMicro: DEFAULT_TEAM_BUDGET_MICRO,
          budgetEnforcement: "hard",
        })
        .returning();
      defaultTeamId = team!.id;
      await seedChatApp(tx, orgId, defaultTeamId);
      role = "owner";
    } else {
      const [org] = await tx.select().from(organizations).limit(1);
      orgId = org!.id;
      const [team] = await tx
        .select()
        .from(teams)
        .where(eq(teams.orgId, orgId))
        .limit(1);
      defaultTeamId = team!.id;
      // first human member becomes owner
      const humans = await tx
        .select({ id: memberships.id })
        .from(memberships)
        .where(eq(memberships.type, "human"));
      role = humans.length === 0 ? "owner" : "member";
    }

    const [membership] = await tx
      .insert(memberships)
      .values({
        orgId,
        userId,
        type: "human",
        role,
        teamId: defaultTeamId,
        teamRole: role === "owner" ? "team_admin" : "member",
      })
      .returning();

    const key = generateApiKey();
    await tx.insert(apiKeys).values({
      orgId,
      ownerMemberId: membership!.id,
      isDefault: true,
      keyHash: key.keyHash,
      keyPrefix: key.keyPrefix,
      createdBy: userId,
    });

    return {
      ctx: {
        membershipId: membership!.id,
        orgId,
        role,
        teamId: defaultTeamId,
      },
      defaultKey: key.plaintext,
    };
  });
}
