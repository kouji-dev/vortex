import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import type Database from 'better-sqlite3';
import { z } from 'zod';
import { STATUS_VALUES, type Status } from './db.js';
import { renderBoardMarkdown } from './markdown.js';
import * as q from './queries.js';

const statusSchema = z.enum(STATUS_VALUES as unknown as [string, ...string[]]);

const listFiltersSchema = z.record(z.string(), z.any()).optional();

function textResult(body: string) {
  return { content: [{ type: 'text' as const, text: body }] };
}

function errText(message: string) {
  return textResult(`Error: ${message}`);
}

function exportBoard(db: Database.Database, epicId?: number, scopeId?: number): string {
  let scopes = q.listScopes(db);
  let epics = q.listEpics(db);

  if (epicId !== undefined) {
    const e = q.getEpic(db, epicId);
    if (!e) return '';
    epics = [e];
    const s = q.getScope(db, e.scope_id);
    scopes = s ? [s] : [];
  } else if (scopeId !== undefined) {
    const s = q.getScope(db, scopeId);
    if (!s) return '';
    scopes = [s];
    epics = q.listEpics(db, { scope_id: scopeId });
  }

  const tickets = q.listTickets(db);
  const byEpic = new Map<number, typeof tickets>();
  for (const t of tickets) {
    if (!epics.some((e) => e.id === t.epic_id)) continue;
    if (!byEpic.has(t.epic_id)) byEpic.set(t.epic_id, []);
    byEpic.get(t.epic_id)!.push(t);
  }
  return renderBoardMarkdown(scopes, epics, byEpic);
}

export function registerEpicTicketTools(server: McpServer, db: Database.Database): void {
  server.registerTool(
    'list_scopes',
    {
      title: 'List scopes',
      description:
        'List scopes (domains). Optional `filters`: object whose keys are allowlisted column names (id, title, description, status, created_at, updated_at). Values: scalar (=), array or { in: [] } (IN), { like: "%pat%" } (LIKE), or null (IS NULL). Multiple keys AND. Omit filters to list all.',
      inputSchema: {
        filters: listFiltersSchema,
      },
    },
    async (args) => {
      try {
        const rows = q.listScopes(db, args?.filters);
        return textResult(JSON.stringify(rows, null, 2));
      } catch (e) {
        return errText(e instanceof Error ? e.message : String(e));
      }
    },
  );

  server.registerTool(
    'create_scope',
    {
      title: 'Create scope',
      description: 'Create a scope — a product/domain bucket that groups EPICs.',
      inputSchema: {
        title: z.string().min(1),
        description: z.string().optional(),
        status: statusSchema.optional(),
      },
    },
    async (args) => {
      try {
        const row = q.createScope(db, {
          ...args,
          status: args.status as Status | undefined,
        });
        return textResult(JSON.stringify(row, null, 2));
      } catch (e) {
        return errText(e instanceof Error ? e.message : String(e));
      }
    },
  );

  server.registerTool(
    'update_scope',
    {
      title: 'Update scope',
      description: 'Update a scope by id.',
      inputSchema: {
        id: z.number().int().positive(),
        title: z.string().min(1).optional(),
        description: z.string().nullable().optional(),
        status: statusSchema.optional(),
      },
    },
    async (args) => {
      try {
        const { id, ...rest } = args;
        const row = q.updateScope(db, id, {
          ...rest,
          status: rest.status as Status | undefined,
        });
        if (!row) return errText(`Scope ${id} not found`);
        return textResult(JSON.stringify(row, null, 2));
      } catch (e) {
        return errText(e instanceof Error ? e.message : String(e));
      }
    },
  );

  server.registerTool(
    'delete_scope',
    {
      title: 'Delete scope',
      description:
        'Delete a scope. All EPICs in that scope and their tickets are removed (cascade).',
      inputSchema: { id: z.number().int().positive() },
    },
    async ({ id }) => {
      const { deleted, epicCount } = q.deleteScope(db, id);
      if (!deleted) return errText(`Scope ${id} not found`);
      return textResult(
        `Deleted scope ${id} (${epicCount} EPIC(s) and their tickets removed via cascade).`,
      );
    },
  );

  server.registerTool(
    'list_epics',
    {
      title: 'List epics',
      description:
        'List EPICs. Optional `filters`: keys are allowlisted columns (id, scope_id, title, description, status, created_at, updated_at). Same value shapes as list_scopes (scalar, array / { in }, { like }, null). AND between keys.',
      inputSchema: {
        filters: listFiltersSchema,
      },
    },
    async (args) => {
      try {
        const rows = q.listEpics(db, args?.filters);
        return textResult(JSON.stringify(rows, null, 2));
      } catch (e) {
        return errText(e instanceof Error ? e.message : String(e));
      }
    },
  );

  server.registerTool(
    'create_epic',
    {
      title: 'Create epic',
      description:
        'Create an EPIC under a scope. Omit scope_id to use the first scope (often the default scope).',
      inputSchema: {
        scope_id: z.number().int().positive().optional(),
        title: z.string().min(1),
        description: z.string().optional(),
        status: statusSchema.optional(),
      },
    },
    async (args) => {
      try {
        const row = q.createEpic(db, {
          ...args,
          status: args.status as Status | undefined,
        });
        return textResult(JSON.stringify(row, null, 2));
      } catch (e) {
        return errText(e instanceof Error ? e.message : String(e));
      }
    },
  );

  server.registerTool(
    'update_epic',
    {
      title: 'Update epic',
      description: 'Update an EPIC by id. Optional scope_id moves the EPIC to another scope.',
      inputSchema: {
        id: z.number().int().positive(),
        scope_id: z.number().int().positive().optional(),
        title: z.string().min(1).optional(),
        description: z.string().nullable().optional(),
        status: statusSchema.optional(),
      },
    },
    async (args) => {
      try {
        const { id, ...rest } = args;
        const row = q.updateEpic(db, id, {
          ...rest,
          status: rest.status as Status | undefined,
        });
        if (!row) return errText(`EPIC ${id} not found`);
        return textResult(JSON.stringify(row, null, 2));
      } catch (e) {
        return errText(e instanceof Error ? e.message : String(e));
      }
    },
  );

  server.registerTool(
    'delete_epic',
    {
      title: 'Delete epic',
      description: 'Delete an EPIC and its tickets (cascade).',
      inputSchema: { id: z.number().int().positive() },
    },
    async ({ id }) => {
      const ok = q.deleteEpic(db, id);
      if (!ok) return errText(`EPIC ${id} not found`);
      return textResult(`Deleted EPIC ${id} (and its tickets).`);
    },
  );

  server.registerTool(
    'list_tickets',
    {
      title: 'List tickets',
      description:
        'List tickets. Optional `filters`: keys are allowlisted columns (id, epic_id, title, description, status, agent, idea, locked, created_at, updated_at). Same value shapes as list_scopes. `locked`: boolean or 0/1 for equality.',
      inputSchema: {
        filters: listFiltersSchema,
      },
    },
    async (args) => {
      try {
        const rows = q.listTickets(db, args?.filters);
        return textResult(JSON.stringify(rows, null, 2));
      } catch (e) {
        return errText(e instanceof Error ? e.message : String(e));
      }
    },
  );

  server.registerTool(
    'create_ticket',
    {
      title: 'Create ticket',
      description: 'Create a ticket under an EPIC. Use agent + idea to capture who should own it and the intent.',
      inputSchema: {
        epic_id: z.number().int().positive(),
        title: z.string().min(1),
        description: z.string().optional(),
        status: statusSchema.optional(),
        agent: z.string().optional(),
        idea: z.string().optional(),
      },
    },
    async (args) => {
      try {
        const row = q.createTicket(db, {
          ...args,
          status: args.status as Status | undefined,
        });
        return textResult(JSON.stringify(row, null, 2));
      } catch (e) {
        return errText(e instanceof Error ? e.message : String(e));
      }
    },
  );

  server.registerTool(
    'update_ticket',
    {
      title: 'Update ticket',
      description:
        'Update a ticket by id. If the ticket is locked, pass actor matching the assigned agent; other agents should only use list/export tools.',
      inputSchema: {
        id: z.number().int().positive(),
        actor: z.string().optional(),
        epic_id: z.number().int().positive().optional(),
        title: z.string().min(1).optional(),
        description: z.string().nullable().optional(),
        status: statusSchema.optional(),
        agent: z.string().nullable().optional(),
        idea: z.string().nullable().optional(),
      },
    },
    async (args) => {
      try {
        const { id, actor, ...rest } = args;
        const row = q.updateTicket(
          db,
          id,
          {
            ...rest,
            status: rest.status as Status | undefined,
          },
          actor,
        );
        if (!row) return errText(`Ticket ${id} not found`);
        return textResult(JSON.stringify(row, null, 2));
      } catch (e) {
        return errText(e instanceof Error ? e.message : String(e));
      }
    },
  );

  server.registerTool(
    'delete_ticket',
    {
      title: 'Delete ticket',
      description:
        'Delete a ticket by id. If locked, pass actor matching the assigned agent.',
      inputSchema: {
        id: z.number().int().positive(),
        actor: z.string().optional(),
      },
    },
    async (args) => {
      try {
        const ok = q.deleteTicket(db, args.id, args.actor);
        if (!ok) return errText(`Ticket ${args.id} not found`);
        return textResult(`Deleted ticket ${args.id}.`);
      } catch (e) {
        return errText(e instanceof Error ? e.message : String(e));
      }
    },
  );

  server.registerTool(
    'set_ticket_lock',
    {
      title: 'Lock or unlock ticket',
      description:
        'Set locked=true so only the assigned agent may update/delete; locked=false to allow collaborative edits again. Only the assigned agent may change the lock. Requires agent to be set on the ticket.',
      inputSchema: {
        id: z.number().int().positive(),
        locked: z.boolean(),
        actor: z.string().min(1),
      },
    },
    async (args) => {
      try {
        const row = q.setTicketLock(db, args.id, args.locked, args.actor);
        return textResult(JSON.stringify(row, null, 2));
      } catch (e) {
        return errText(e instanceof Error ? e.message : String(e));
      }
    },
  );

  server.registerTool(
    'export_board_markdown',
    {
      title: 'Export board as Markdown',
      description:
        'Render scopes, epics, and tickets as Markdown. Optional epic_id (one EPIC) or scope_id (one scope); if both omitted, full board.',
      inputSchema: {
        epic_id: z.number().int().positive().optional(),
        scope_id: z.number().int().positive().optional(),
      },
    },
    async (args) => {
      const epicId = args?.epic_id;
      const scopeId = args?.scope_id;
      if (epicId !== undefined && scopeId !== undefined) {
        return errText('Pass at most one of epic_id or scope_id.');
      }
      const md = exportBoard(db, epicId, scopeId);
      if (epicId !== undefined && md === '') return errText(`EPIC ${epicId} not found`);
      if (scopeId !== undefined && md === '') return errText(`Scope ${scopeId} not found`);
      return textResult(md);
    },
  );
}

export function createMcpServer(db: Database.Database): McpServer {
  const server = new McpServer({
    name: 'task-manager',
    version: '0.5.0',
  });
  registerEpicTicketTools(server, db);
  return server;
}
