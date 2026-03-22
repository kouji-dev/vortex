import { assertStatus, type Status } from './db.js';

export type ListEntity = 'scopes' | 'epics' | 'tickets';

/** Allowlisted columns per table (SQL identifiers). */
const COLUMNS: Record<ListEntity, ReadonlySet<string>> = {
  scopes: new Set(['id', 'title', 'description', 'status', 'created_at', 'updated_at']),
  epics: new Set(['id', 'scope_id', 'title', 'description', 'status', 'created_at', 'updated_at']),
  tickets: new Set([
    'id',
    'epic_id',
    'title',
    'description',
    'status',
    'agent',
    'idea',
    'locked',
    'created_at',
    'updated_at',
  ]),
};

const INTEGER_COLUMNS = new Set([
  'id',
  'scope_id',
  'epic_id',
  'locked',
]);

function sqlIdent(col: string): string {
  if (!/^[a-z_][a-z0-9_]*$/i.test(col)) {
    throw new Error(`Invalid column name: ${col}`);
  }
  return col;
}

function lockedParam(raw: unknown): number {
  if (raw === true || raw === 1) return 1;
  if (raw === false || raw === 0) return 0;
  throw new Error(`Column "locked": use boolean or 0/1, got ${JSON.stringify(raw)}`);
}

function intParam(col: string, raw: unknown): number {
  const n = typeof raw === 'number' ? raw : Number(raw);
  if (!Number.isFinite(n) || !Number.isInteger(n)) {
    throw new Error(`Column "${col}" expects an integer`);
  }
  return n;
}

function normalizeScalar(col: string, raw: unknown): unknown {
  if (INTEGER_COLUMNS.has(col) && col !== 'locked') {
    return intParam(col, raw);
  }
  if (col === 'status') {
    const s = String(raw);
    assertStatus(s);
    return s as Status;
  }
  return raw;
}

function normalizeList(col: string, values: unknown[]): unknown[] {
  return values.map((v) => {
    if (col === 'locked') return lockedParam(v);
    return normalizeScalar(col, v);
  });
}

/**
 * Build a parameterized WHERE clause from a generic filter object.
 *
 * - **Key** = column name (must be allowlisted for the entity).
 * - **Value**:
 *   - `null` → `IS NULL`
 *   - **array** (non-empty) → `IN (?, …)`
 *   - `{ "like": "%pat%" }` → `LIKE ? ESCAPE '\'` (SQLite `LIKE` is ASCII case-insensitive by default)
 *   - `{ "in": [ … ] }` → same as array
 *   - **scalar** → `= ?` (`status` validated; `locked`: boolean or 0/1; integer cols coerced)
 *
 * Multiple keys are combined with **AND**.
 */
export function buildListWhere(
  entity: ListEntity,
  filters: Record<string, unknown> | undefined,
): { sqlFragment: string; params: unknown[] } {
  const allowed = COLUMNS[entity];
  if (!filters || Object.keys(filters).length === 0) {
    return { sqlFragment: '', params: [] };
  }

  const conditions: string[] = [];
  const params: unknown[] = [];

  for (const [col, raw] of Object.entries(filters)) {
    if (!allowed.has(col)) {
      const ok = [...allowed].sort().join(', ');
      throw new Error(`Disallowed column "${col}" for ${entity}. Allowed: ${ok}`);
    }

    const ident = sqlIdent(col);

    if (raw === undefined) {
      continue;
    }

    if (raw === null) {
      conditions.push(`${ident} IS NULL`);
      continue;
    }

    if (Array.isArray(raw)) {
      if (raw.length === 0) {
        throw new Error(`Column "${col}": empty array (IN requires at least one value)`);
      }
      if (col === 'status') {
        for (const v of raw) assertStatus(String(v));
      }
      const placeholders = raw.map(() => '?').join(', ');
      conditions.push(`${ident} IN (${placeholders})`);
      params.push(...normalizeList(col, raw));
      continue;
    }

    if (typeof raw === 'object' && raw !== null) {
      const o = raw as Record<string, unknown>;
      const keys = Object.keys(o);
      if (keys.length === 1 && keys[0] === 'like' && typeof o.like === 'string') {
        conditions.push(`${ident} LIKE ? ESCAPE '\\'`);
        params.push(o.like);
        continue;
      }
      if (keys.length === 1 && keys[0] === 'in' && Array.isArray(o.in)) {
        if (o.in.length === 0) {
          throw new Error(`Column "${col}": empty { in: [] }`);
        }
        if (col === 'status') {
          for (const v of o.in) assertStatus(String(v));
        }
        const placeholders = o.in.map(() => '?').join(', ');
        conditions.push(`${ident} IN (${placeholders})`);
        params.push(...normalizeList(col, o.in));
        continue;
      }
      throw new Error(
        `Column "${col}": object value must be { like: string } or { in: array }, got ${JSON.stringify(raw)}`,
      );
    }

    if (col === 'locked') {
      conditions.push(`${ident} = ?`);
      params.push(lockedParam(raw));
      continue;
    }

    conditions.push(`${ident} = ?`);
    params.push(normalizeScalar(col, raw));
  }

  const sqlFragment = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
  return { sqlFragment, params };
}
