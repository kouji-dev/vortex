import { eq, and, or, inArray } from "drizzle-orm";
import { withOrg, apps, appAccess, memberships } from "@vortex/db";
import type { MemberContext } from "../provisioning/provisioning.service.js";
import type { CreateApp } from "@vortex/shared";
import { assertServiceQuota } from "../../shared/caps.js";
import type { Page } from "../../shared/pagination.js";
import { isOrgManager } from "../../shared/rbac.js";

/** Apps the member may see: owner/admin → all; else owned + granted (member/team). */
export async function listAccessibleApps(member: MemberContext, page: Page) {
  return withOrg(member.orgId, async (tx) => {
    if (isOrgManager(member)) {
      return tx.select().from(apps).limit(page.limit).offset(page.offset);
    }
    const grants = await tx
      .select({ appId: appAccess.appId })
      .from(appAccess)
      .where(
        or(
          and(
            eq(appAccess.principalType, "member"),
            eq(appAccess.principalId, member.membershipId),
          ),
          member.teamId
            ? and(
                eq(appAccess.principalType, "team"),
                eq(appAccess.principalId, member.teamId),
              )
            : undefined,
        ),
      );
    const grantedIds = grants.map((g) => g.appId);
    return tx
      .select()
      .from(apps)
      .where(
        or(
          eq(apps.ownerMemberId, member.membershipId),
          grantedIds.length ? inArray(apps.id, grantedIds) : undefined,
        ),
      )
      .limit(page.limit)
      .offset(page.offset);
  });
}

/**
 * Create a service or personal app.
 * - service: auto-provision a technical member in the creator's team, wire it as
 *   the app's `technicalMemberId`.
 * - personal: owned by `ownerMemberId` (defaults to the creator).
 */
export async function createApp(member: MemberContext, input: CreateApp) {
  // Per-member service-account quota (Free = 1). Checked before we mutate.
  if (input.kind === "service") {
    await assertServiceQuota(member.orgId, member.membershipId);
  }
  return withOrg(member.orgId, async (tx) => {
    let technicalMemberId: string | null = null;
    let ownerMemberId: string | null = null;

    if (input.kind === "service" || input.kind === "system") {
      const [tech] = await tx
        .insert(memberships)
        .values({
          orgId: member.orgId,
          type: "technical",
          teamId: member.teamId,
          teamRole: "member",
        })
        .returning();
      technicalMemberId = tech!.id;
      // The creator owns their service apps → drives the per-member quota + access.
      if (input.kind === "service") ownerMemberId = member.membershipId;
    } else {
      ownerMemberId = input.ownerMemberId ?? member.membershipId;
    }

    const [app] = await tx
      .insert(apps)
      .values({
        orgId: member.orgId,
        name: input.name,
        kind: input.kind,
        ownerMemberId,
        technicalMemberId,
        defaultRoutingPolicy: input.defaultRoutingPolicy ?? null,
      })
      .returning();
    return app!;
  });
}

/**
 * May the caller edit this app (grant/revoke access, etc.)? Org owner/admin, the
 * app's `ownerMemberId`, or a member/team holding an `app_admin` grant. A plain
 * `app_member` grant is not enough.
 */
export async function canManageApp(
  member: MemberContext,
  appId: string,
): Promise<boolean> {
  if (isOrgManager(member)) return true;
  return withOrg(member.orgId, async (tx) => {
    const [app] = await tx
      .select({ ownerMemberId: apps.ownerMemberId })
      .from(apps)
      .where(and(eq(apps.id, appId), eq(apps.orgId, member.orgId)))
      .limit(1);
    if (!app) return false;
    if (app.ownerMemberId && app.ownerMemberId === member.membershipId)
      return true;
    const [grant] = await tx
      .select({ id: appAccess.id })
      .from(appAccess)
      .where(
        and(
          eq(appAccess.appId, appId),
          eq(appAccess.role, "app_admin"),
          or(
            and(
              eq(appAccess.principalType, "member"),
              eq(appAccess.principalId, member.membershipId),
            ),
            member.teamId
              ? and(
                  eq(appAccess.principalType, "team"),
                  eq(appAccess.principalId, member.teamId),
                )
              : undefined,
          ),
        ),
      )
      .limit(1);
    return !!grant;
  });
}

/** Fetch one app scoped to the org. */
export async function getApp(orgId: string, id: string) {
  return withOrg(orgId, async (tx) => {
    const [app] = await tx
      .select()
      .from(apps)
      .where(and(eq(apps.id, id), eq(apps.orgId, orgId)))
      .limit(1);
    return app ?? null;
  });
}
