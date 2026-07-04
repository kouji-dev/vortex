import { desc, eq } from "drizzle-orm";
import { createHash } from "node:crypto";
import { withOrg, auditLogs } from "@vortex/db";

/** Append a tamper-evident, hash-chained audit entry for an org. */
export async function appendAudit(a: {
  orgId: string;
  actor?: string | null;
  action: string;
  target?: string | null;
  metadata?: Record<string, unknown>;
}): Promise<void> {
  await withOrg(a.orgId, async (tx) => {
    const [last] = await tx
      .select({ h: auditLogs.entryHash })
      .from(auditLogs)
      .where(eq(auditLogs.orgId, a.orgId))
      .orderBy(desc(auditLogs.createdAt))
      .limit(1);
    const prevHash = last?.h ?? null;
    const payload = JSON.stringify({
      orgId: a.orgId,
      actor: a.actor ?? null,
      action: a.action,
      target: a.target ?? null,
      metadata: a.metadata ?? {},
      prevHash,
    });
    const entryHash = createHash("sha256").update(payload).digest("hex");
    await tx.insert(auditLogs).values({
      orgId: a.orgId,
      actor: a.actor ?? null,
      action: a.action,
      target: a.target ?? null,
      metadata: a.metadata ?? {},
      prevHash,
      entryHash,
    });
  });
}
