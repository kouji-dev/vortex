import type Database from 'better-sqlite3';
import { assertStatus, type EpicRow, type ScopeRow, type Status, type TicketRow } from './db.js';

function agentsMatch(assigned: string, actor: string): boolean {
  return assigned.trim().toLowerCase() === actor.trim().toLowerCase();
}

/** Optional filters for `list_scopes` (AND semantics when multiple set). */
export type ListScopesFilter = {
  status?: Status;
};

export function listScopes(db: Database.Database, filter?: ListScopesFilter): ScopeRow[] {
  if (filter?.status !== undefined) {
    assertStatus(filter.status);
    return db
      .prepare(`SELECT * FROM scopes WHERE status = ? ORDER BY id ASC`)
      .all(filter.status) as ScopeRow[];
  }
  return db.prepare(`SELECT * FROM scopes ORDER BY id ASC`).all() as ScopeRow[];
}

export function getScope(db: Database.Database, id: number): ScopeRow | undefined {
  return db.prepare(`SELECT * FROM scopes WHERE id = ?`).get(id) as ScopeRow | undefined;
}

export function createScope(
  db: Database.Database,
  input: { title: string; description?: string | null; status?: Status },
): ScopeRow {
  assertStatus(input.status ?? 'backlog');
  const info = db
    .prepare(
      `INSERT INTO scopes (title, description, status) VALUES (@title, @description, @status)`,
    )
    .run({
      title: input.title,
      description: input.description ?? null,
      status: input.status ?? 'backlog',
    });
  const row = getScope(db, Number(info.lastInsertRowid));
  if (!row) throw new Error('Failed to read scope after insert');
  return row;
}

export function updateScope(
  db: Database.Database,
  id: number,
  patch: Partial<Pick<ScopeRow, 'title' | 'description' | 'status'>>,
): ScopeRow | undefined {
  if (patch.status !== undefined) assertStatus(patch.status);
  const existing = getScope(db, id);
  if (!existing) return undefined;

  const next = {
    title: patch.title ?? existing.title,
    description: patch.description !== undefined ? patch.description : existing.description,
    status: patch.status ?? existing.status,
  };

  db.prepare(
    `UPDATE scopes SET title = @title, description = @description, status = @status, updated_at = datetime('now') WHERE id = @id`,
  ).run({ ...next, id });
  return getScope(db, id);
}

export function deleteScope(db: Database.Database, id: number): { deleted: boolean; epicCount: number } {
  const epicCount = (
    db.prepare(`SELECT COUNT(*) as c FROM epics WHERE scope_id = ?`).get(id) as { c: number }
  ).c;
  const info = db.prepare(`DELETE FROM scopes WHERE id = ?`).run(id);
  return { deleted: info.changes > 0, epicCount };
}

/** First scope by id (used when MCP omits scope_id). */
export function defaultScopeId(db: Database.Database): number {
  const row = db.prepare(`SELECT id FROM scopes ORDER BY id ASC LIMIT 1`).get() as
    | { id: number }
    | undefined;
  if (!row) throw new Error('No scopes in database');
  return row.id;
}

/** Optional filters for `list_epics` (AND semantics when multiple set). */
export type ListEpicsFilter = {
  scope_id?: number;
  status?: Status;
};

export function listEpics(db: Database.Database, filter?: ListEpicsFilter): EpicRow[] {
  const scopeId = filter?.scope_id;
  const status = filter?.status;
  if (status !== undefined) assertStatus(status);

  if (scopeId !== undefined && status !== undefined) {
    return db
      .prepare(`SELECT * FROM epics WHERE scope_id = ? AND status = ? ORDER BY id ASC`)
      .all(scopeId, status) as EpicRow[];
  }
  if (scopeId !== undefined) {
    return db
      .prepare(`SELECT * FROM epics WHERE scope_id = ? ORDER BY id ASC`)
      .all(scopeId) as EpicRow[];
  }
  if (status !== undefined) {
    return db
      .prepare(`SELECT * FROM epics WHERE status = ? ORDER BY id ASC`)
      .all(status) as EpicRow[];
  }
  return db.prepare(`SELECT * FROM epics ORDER BY id ASC`).all() as EpicRow[];
}

export function getEpic(db: Database.Database, id: number): EpicRow | undefined {
  return db.prepare(`SELECT * FROM epics WHERE id = ?`).get(id) as EpicRow | undefined;
}

export function createEpic(
  db: Database.Database,
  input: {
    scope_id?: number;
    title: string;
    description?: string | null;
    status?: Status;
  },
): EpicRow {
  const scopeId = input.scope_id ?? defaultScopeId(db);
  const scope = getScope(db, scopeId);
  if (!scope) throw new Error(`Scope ${scopeId} not found`);

  assertStatus(input.status ?? 'backlog');
  const info = db
    .prepare(
      `INSERT INTO epics (scope_id, title, description, status) VALUES (@scope_id, @title, @description, @status)`,
    )
    .run({
      scope_id: scopeId,
      title: input.title,
      description: input.description ?? null,
      status: input.status ?? 'backlog',
    });
  const row = getEpic(db, Number(info.lastInsertRowid));
  if (!row) throw new Error('Failed to read epic after insert');
  return row;
}

export function updateEpic(
  db: Database.Database,
  id: number,
  patch: Partial<Pick<EpicRow, 'scope_id' | 'title' | 'description' | 'status'>>,
): EpicRow | undefined {
  if (patch.status !== undefined) assertStatus(patch.status);
  const existing = getEpic(db, id);
  if (!existing) return undefined;

  if (patch.scope_id !== undefined) {
    const s = getScope(db, patch.scope_id);
    if (!s) throw new Error(`Scope ${patch.scope_id} not found`);
  }

  const next = {
    scope_id: patch.scope_id ?? existing.scope_id,
    title: patch.title ?? existing.title,
    description: patch.description !== undefined ? patch.description : existing.description,
    status: patch.status ?? existing.status,
  };

  db.prepare(
    `UPDATE epics SET scope_id = @scope_id, title = @title, description = @description, status = @status, updated_at = datetime('now') WHERE id = @id`,
  ).run({ ...next, id });
  return getEpic(db, id);
}

export function deleteEpic(db: Database.Database, id: number): boolean {
  const info = db.prepare(`DELETE FROM epics WHERE id = ?`).run(id);
  return info.changes > 0;
}

/** Optional filters for `list_tickets` (AND semantics when multiple set). */
export type ListTicketsFilter = {
  epic_id?: number;
  status?: Status;
  /** When set, matches rows where `locked` is 0 or 1. */
  locked?: boolean;
  /** Case-insensitive match on trimmed `agent`; ignored if empty after trim. */
  agent?: string;
};

export function listTickets(db: Database.Database, filter?: ListTicketsFilter): TicketRow[] {
  if (filter?.status !== undefined) assertStatus(filter.status);

  const conditions: string[] = [];
  const params: unknown[] = [];

  if (filter?.epic_id !== undefined) {
    conditions.push('epic_id = ?');
    params.push(filter.epic_id);
  }
  if (filter?.status !== undefined) {
    conditions.push('status = ?');
    params.push(filter.status);
  }
  if (filter?.locked !== undefined) {
    conditions.push('locked = ?');
    params.push(filter.locked ? 1 : 0);
  }
  const agentTrim = filter?.agent?.trim();
  if (agentTrim) {
    conditions.push('LOWER(TRIM(COALESCE(agent, \'\'))) = LOWER(?)');
    params.push(agentTrim);
  }

  const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
  const stmt = db.prepare(`SELECT * FROM tickets ${where} ORDER BY id ASC`);
  return (params.length > 0 ? stmt.all(...params) : stmt.all()) as TicketRow[];
}

export function getTicket(db: Database.Database, id: number): TicketRow | undefined {
  return db.prepare(`SELECT * FROM tickets WHERE id = ?`).get(id) as TicketRow | undefined;
}

export function createTicket(
  db: Database.Database,
  input: {
    epic_id: number;
    title: string;
    description?: string | null;
    status?: Status;
    agent?: string | null;
    idea?: string | null;
    locked?: boolean;
  },
): TicketRow {
  assertStatus(input.status ?? 'backlog');
  const info = db
    .prepare(
      `INSERT INTO tickets (epic_id, title, description, status, agent, idea, locked) VALUES (@epic_id, @title, @description, @status, @agent, @idea, @locked)`,
    )
    .run({
      epic_id: input.epic_id,
      title: input.title,
      description: input.description ?? null,
      status: input.status ?? 'backlog',
      agent: input.agent ?? null,
      idea: input.idea ?? null,
      locked: input.locked ? 1 : 0,
    });
  const row = getTicket(db, Number(info.lastInsertRowid));
  if (!row) throw new Error('Failed to read ticket after insert');
  return row;
}

export function setTicketLock(
  db: Database.Database,
  id: number,
  locked: boolean,
  actor: string,
): TicketRow {
  const existing = getTicket(db, id);
  if (!existing) throw new Error(`Ticket ${id} not found`);
  const assigned = (existing.agent ?? '').trim();
  const who = actor.trim();
  if (!assigned) throw new Error('Set agent on the ticket before locking');
  if (!agentsMatch(assigned, who)) {
    throw new Error(`Only assigned agent "${assigned}" may change lock`);
  }
  db.prepare(`UPDATE tickets SET locked = ?, updated_at = datetime('now') WHERE id = ?`).run(
    locked ? 1 : 0,
    id,
  );
  const row = getTicket(db, id);
  if (!row) throw new Error('Failed after lock update');
  return row;
}

export function updateTicket(
  db: Database.Database,
  id: number,
  patch: Partial<
    Pick<TicketRow, 'epic_id' | 'title' | 'description' | 'status' | 'agent' | 'idea' | 'locked'>
  >,
  actor?: string | null,
): TicketRow | undefined {
  if (patch.status !== undefined) assertStatus(patch.status);
  const existing = getTicket(db, id);
  if (!existing) return undefined;

  if (existing.locked === 1) {
    const assigned = (existing.agent ?? '').trim();
    const who = (actor ?? '').trim();
    if (!assigned || !agentsMatch(assigned, who)) {
      throw new Error(
        `Ticket ${id} is locked to agent "${assigned}". Pass actor matching agent to update.`,
      );
    }
  }

  if (patch.epic_id !== undefined) {
    const epic = getEpic(db, patch.epic_id);
    if (!epic) throw new Error(`EPIC ${patch.epic_id} not found`);
  }

  const next = {
    epic_id: patch.epic_id ?? existing.epic_id,
    title: patch.title ?? existing.title,
    description: patch.description !== undefined ? patch.description : existing.description,
    status: patch.status ?? existing.status,
    agent: patch.agent !== undefined ? patch.agent : existing.agent,
    idea: patch.idea !== undefined ? patch.idea : existing.idea,
    locked:
      patch.locked !== undefined ? (patch.locked ? 1 : 0) : (existing.locked as 0 | 1),
  };

  db.prepare(
    `UPDATE tickets SET epic_id = @epic_id, title = @title, description = @description, status = @status, agent = @agent, idea = @idea, locked = @locked, updated_at = datetime('now') WHERE id = @id`,
  ).run({ ...next, id });
  return getTicket(db, id);
}

export function deleteTicket(db: Database.Database, id: number, actor?: string | null): boolean {
  const existing = getTicket(db, id);
  if (!existing) return false;
  if (existing.locked === 1) {
    const assigned = (existing.agent ?? '').trim();
    const who = (actor ?? '').trim();
    if (!assigned || !agentsMatch(assigned, who)) {
      throw new Error(
        `Ticket ${id} is locked to agent "${assigned}". Pass actor matching agent to delete.`,
      );
    }
  }
  const info = db.prepare(`DELETE FROM tickets WHERE id = ?`).run(id);
  return info.changes > 0;
}
