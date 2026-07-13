import { desc, eq, sql } from "drizzle-orm";
import { createHash } from "node:crypto";
import { withOrg, auditLogs, type Tx } from "@vortex/db";

/**
 * Serialize hash-chained appends inside `tx`:
 * 1. takes a transaction-scoped advisory lock on `lockKey` (first statement in
 *    the tx — concurrent writers to the same chain queue up here, so the
 *    prev-hash read is race-free),
 * 2. reads the previous entry hash via `getPrev` (order by (createdAt, id)
 *    descending for a deterministic tail),
 * 3. computes entryHash = sha256(payload + prevHash) and runs `insert`.
 *
 * Shared by the org audit log ('audit:{orgId}') and the platform audit log
 * ('audit:platform').
 */
export async function hashChainedInsert(
  tx: Tx,
  a: {
    lockKey: string;
    payload: Record<string, unknown>;
    getPrev: () => Promise<string | null>;
    insert: (prevHash: string | null, entryHash: string) => Promise<void>;
  },
): Promise<void> {
  await tx.execute(sql`select pg_advisory_xact_lock(hashtext(${a.lockKey}))`);
  const prevHash = await a.getPrev();
  const entryHash = createHash("sha256")
    .update(JSON.stringify({ ...a.payload, prevHash }))
    .digest("hex");
  await a.insert(prevHash, entryHash);
}

/** Append a tamper-evident, hash-chained audit entry for an org. */
export async function appendAudit(a: {
  orgId: string;
  actor?: string | null;
  action: string;
  target?: string | null;
  metadata?: Record<string, unknown>;
}): Promise<void> {
  await withOrg(a.orgId, (tx) =>
    hashChainedInsert(tx, {
      lockKey: `audit:${a.orgId}`,
      payload: {
        orgId: a.orgId,
        actor: a.actor ?? null,
        action: a.action,
        target: a.target ?? null,
        metadata: a.metadata ?? {},
      },
      getPrev: async () => {
        const [last] = await tx
          .select({ h: auditLogs.entryHash })
          .from(auditLogs)
          .where(eq(auditLogs.orgId, a.orgId))
          .orderBy(desc(auditLogs.createdAt), desc(auditLogs.id))
          .limit(1);
        return last?.h ?? null;
      },
      insert: async (prevHash, entryHash) => {
        await tx.insert(auditLogs).values({
          orgId: a.orgId,
          actor: a.actor ?? null,
          action: a.action,
          target: a.target ?? null,
          metadata: a.metadata ?? {},
          prevHash,
          entryHash,
        });
      },
    }),
  );
}
