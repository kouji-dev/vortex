import { and, eq, count } from "drizzle-orm";
import { withBypass, withOrg, memberships, apps } from "@vortex/db";
import { resolveEntitlements } from "./entitlements.js";

/** A plan seat/service quota was hit. Routes map this to HTTP 403. */
export class CapExceededError extends Error {
  cap: string;
  constructor(cap: string, message?: string) {
    super(message ?? `plan limit reached: ${cap}`);
    this.name = "CapExceededError";
    this.cap = cap;
  }
}

/** Block adding a human seat beyond the plan's seatsPerOrg (null = unlimited). */
export async function assertSeatAvailable(orgId: string): Promise<void> {
  const ent = await resolveEntitlements(orgId);
  if (ent.seatsPerOrg == null) return;
  const rows = await withBypass((tx) =>
    tx
      .select({ n: count() })
      .from(memberships)
      .where(and(eq(memberships.orgId, orgId), eq(memberships.type, "human"))),
  );
  const n = rows[0]?.n ?? 0;
  if (n >= ent.seatsPerOrg) {
    throw new CapExceededError("seats", `seat limit reached (${ent.seatsPerOrg})`);
  }
}

/** Block a member creating a service account beyond servicePerMember (null = unlimited). */
export async function assertServiceQuota(
  orgId: string,
  memberId: string,
): Promise<void> {
  const ent = await resolveEntitlements(orgId);
  if (ent.servicePerMember == null) return;
  const rows = await withOrg(orgId, (tx) =>
    tx
      .select({ n: count() })
      .from(apps)
      .where(and(eq(apps.kind, "service"), eq(apps.ownerMemberId, memberId))),
  );
  const n = rows[0]?.n ?? 0;
  if (n >= ent.servicePerMember) {
    throw new CapExceededError(
      "services",
      `service limit per member reached (${ent.servicePerMember})`,
    );
  }
}
