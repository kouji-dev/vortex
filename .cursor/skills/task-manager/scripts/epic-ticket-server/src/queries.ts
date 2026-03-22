import type Database from 'better-sqlite3';
import { assertStatus, type EpicRow, type ScopeRow, type Status, type TicketRow } from './db.js';
import { buildListWhere } from './whereBuilder.js';

function agentsMatch(assigned: string, actor: string): boolean {
  return assigned.trim().toLowerCase() === actor.trim().toLowerCase();
}

/** Generic list filters: keys are allowlisted columns; see `whereBuilder` / MCP docs. */
export type ListRowFilters = Record<string, unknown>;

export function listScopes(db: Database.Database, filters?: ListRowFilters): ScopeRow[] {
  const { sqlFragment, params } = buildListWhere('scopes', filters);
  const sql = `SELECT * FROM scopes${sqlFragment ? ` ${sqlFragment}` : ''} ORDER BY id ASC`;
  const stmt = db.prepare(sql);
  return (params.length > 0 ? stmt.all(...params) : stmt.all()) as ScopeRow[];
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

export function listEpics(db: Database.Database, filters?: ListRowFilters): EpicRow[] {
  const { sqlFragment, params } = buildListWhere('epics', filters);
  const sql = `SELECT * FROM epics${sqlFragment ? ` ${sqlFragment}` : ''} ORDER BY id ASC`;
  const stmt = db.prepare(sql);
  return (params.length > 0 ? stmt.all(...params) : stmt.all()) as EpicRow[];
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

export function listTickets(db: Database.Database, filters?: ListRowFilters): TicketRow[] {
  const { sqlFragment, params } = buildListWhere('tickets', filters);
  const sql = `SELECT * FROM tickets${sqlFragment ? ` ${sqlFragment}` : ''} ORDER BY id ASC`;
  const stmt = db.prepare(sql);
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
