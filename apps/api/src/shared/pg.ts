/**
 * Is this a Postgres unique-constraint violation (SQLSTATE 23505)?
 * Pass `constraint` to match a specific index/constraint name — useful when a
 * table has several unique constraints and only one signals "already exists".
 *
 *   try { await tx.insert(…) } catch (e) {
 *     if (isUniqueViolation(e, "credit_ledger_request_id_uq")) return; // idempotent replay
 *     throw e;
 *   }
 */
export function isUniqueViolation(e: unknown, constraint?: string): boolean {
  if (typeof e !== "object" || e === null) return false;
  const err = e as {
    code?: unknown;
    constraint_name?: unknown;
    constraint?: unknown;
    message?: unknown;
  };
  if (err.code !== "23505") return false;
  if (!constraint) return true;
  // postgres.js exposes `constraint_name`; node-postgres exposes `constraint`.
  const name = err.constraint_name ?? err.constraint;
  if (typeof name === "string") return name === constraint;
  return typeof err.message === "string" && err.message.includes(constraint);
}
