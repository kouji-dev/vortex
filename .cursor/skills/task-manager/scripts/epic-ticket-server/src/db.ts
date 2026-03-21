import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import Database from 'better-sqlite3';

export const STATUS_VALUES = [
  'backlog',
  'ready',
  'in_progress',
  'blocked',
  'done',
  'cancelled',
] as const;

export type Status = (typeof STATUS_VALUES)[number];

export type ScopeRow = {
  id: number;
  title: string;
  description: string | null;
  status: Status;
  created_at: string;
  updated_at: string;
};

export type EpicRow = {
  id: number;
  scope_id: number;
  title: string;
  description: string | null;
  status: Status;
  created_at: string;
  updated_at: string;
};

export type TicketRow = {
  id: number;
  epic_id: number;
  title: string;
  description: string | null;
  status: Status;
  agent: string | null;
  idea: string | null;
  /** When 1, only the assigned agent may update/delete (pass matching actor). */
  locked: number;
  created_at: string;
  updated_at: string;
};

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export function defaultDbPath(): string {
  const fromEnv = process.env.EPIC_TICKET_DB;
  if (fromEnv && fromEnv.trim()) return path.resolve(fromEnv);
  return path.join(__dirname, '..', 'data', 'epic-tickets.db');
}

export function openDatabase(dbPath = defaultDbPath()): Database.Database {
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  const db = new Database(dbPath);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');
  migrate(db);
  return db;
}

function migrate(db: Database.Database): void {
  db.exec(`
    CREATE TABLE IF NOT EXISTS scopes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      description TEXT,
      status TEXT NOT NULL DEFAULT 'backlog',
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS epics (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      description TEXT,
      status TEXT NOT NULL DEFAULT 'backlog',
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS tickets (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      epic_id INTEGER NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
      title TEXT NOT NULL,
      description TEXT,
      status TEXT NOT NULL DEFAULT 'backlog',
      agent TEXT,
      idea TEXT,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_tickets_epic ON tickets(epic_id);
    CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
  `);
  ensureTicketLockedColumn(db);
  ensureEpicScopeColumn(db);
}

function ensureTicketLockedColumn(db: Database.Database): void {
  const cols = db.prepare(`PRAGMA table_info(tickets)`).all() as { name: string }[];
  if (!cols.some((c) => c.name === 'locked')) {
    db.exec(`ALTER TABLE tickets ADD COLUMN locked INTEGER NOT NULL DEFAULT 0`);
  }
}

/** Links epics → scopes; backfills a default scope for existing DBs. */
function ensureEpicScopeColumn(db: Database.Database): void {
  const epicCols = db.prepare(`PRAGMA table_info(epics)`).all() as { name: string }[];
  if (!epicCols.some((c) => c.name === 'scope_id')) {
    db.exec(`ALTER TABLE epics ADD COLUMN scope_id INTEGER REFERENCES scopes(id) ON DELETE CASCADE`);
  }

  const scopeCount = db.prepare(`SELECT COUNT(*) as c FROM scopes`).get() as { c: number };
  if (scopeCount.c === 0) {
    db.prepare(`INSERT INTO scopes (title, description, status) VALUES (?, ?, ?)`).run(
      'Default',
      'Auto-created for boards without an explicit scope.',
      'backlog',
    );
  }

  const firstScope = db.prepare(`SELECT id FROM scopes ORDER BY id ASC LIMIT 1`).get() as { id: number };
  db.prepare(`UPDATE epics SET scope_id = ? WHERE scope_id IS NULL`).run(firstScope.id);

  db.exec(`CREATE INDEX IF NOT EXISTS idx_epics_scope ON epics(scope_id)`);
}

export function assertStatus(s: string): asserts s is Status {
  if (!STATUS_VALUES.includes(s as Status)) {
    throw new Error(`Invalid status "${s}". Use one of: ${STATUS_VALUES.join(', ')}`);
  }
}
