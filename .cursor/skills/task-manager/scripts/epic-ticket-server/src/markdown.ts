import type { EpicRow, ScopeRow, TicketRow } from './db.js';

export function renderBoardMarkdown(
  scopes: ScopeRow[],
  epics: EpicRow[],
  ticketsByEpic: Map<number, TicketRow[]>,
): string {
  const lines: string[] = ['# Scope / EPIC / ticket board', ''];

  const scopeById = new Map(scopes.map((s) => [s.id, s]));
  const epicsByScope = new Map<number, EpicRow[]>();
  for (const e of epics) {
    if (!epicsByScope.has(e.scope_id)) epicsByScope.set(e.scope_id, []);
    epicsByScope.get(e.scope_id)!.push(e);
  }

  if (scopes.length === 0 && epics.length === 0) {
    lines.push('_No scopes or epics yet._', '');
    return lines.join('\n');
  }

  const orderedScopeIds = [...new Set([...scopes.map((s) => s.id), ...epics.map((e) => e.scope_id)])].sort(
    (a, b) => a - b,
  );

  for (const sid of orderedScopeIds) {
    const scope = scopeById.get(sid);
    const scopeEpics = epicsByScope.get(sid) ?? [];
    if (scope) {
      lines.push(`## SCOPE ${scope.id}: ${escapeMdInline(scope.title)}`);
      lines.push('');
      lines.push(`- **Status:** \`${scope.status}\``);
      if (scope.description) {
        lines.push('');
        lines.push(scope.description.trim());
      }
      lines.push('');
    } else if (scopeEpics.length > 0) {
      lines.push(`## SCOPE ${sid}: _(missing scope row)_`);
      lines.push('');
    }

    if (scopeEpics.length === 0) {
      lines.push('_No epics in this scope._', '');
      continue;
    }

    for (const epic of scopeEpics) {
      lines.push(`### EPIC ${epic.id}: ${escapeMdInline(epic.title)}`);
      lines.push('');
      lines.push(`- **Scope:** ${epic.scope_id} · **Status:** \`${epic.status}\``);
      if (epic.description) {
        lines.push('');
        lines.push(epic.description.trim());
      }
      lines.push('');
      const tickets = ticketsByEpic.get(epic.id) ?? [];
      if (tickets.length === 0) {
        lines.push('_No tickets._', '');
        continue;
      }
      lines.push('| ID | Title | Status | Locked | Agent | Idea |');
      lines.push('| --- | --- | --- | --- | --- | --- |');
      for (const t of tickets) {
        const locked = t.locked ? 'yes' : 'no';
        lines.push(
          `| ${t.id} | ${escapeMdCell(t.title)} | \`${t.status}\` | ${locked} | ${escapeMdCell(t.agent ?? '')} | ${escapeMdCell(t.idea ?? '')} |`,
        );
      }
      lines.push('');
      for (const t of tickets) {
        lines.push(`#### Ticket ${t.id}: ${escapeMdInline(t.title)}`);
        lines.push('');
        lines.push(
          `- **EPIC:** ${epic.id} · **Status:** \`${t.status}\` · **Locked:** ${t.locked ? 'yes' : 'no'}`,
        );
        if (t.agent) lines.push(`- **Agent:** ${t.agent}`);
        if (t.idea) lines.push(`- **Idea:** ${t.idea}`);
        if (t.description) {
          lines.push('');
          lines.push(t.description.trim());
        }
        lines.push('');
      }
    }
  }

  return lines.join('\n').trimEnd() + '\n';
}

function escapeMdInline(s: string): string {
  return s.replace(/\r?\n/g, ' ').replace(/\|/g, '\\|');
}

function escapeMdCell(s: string): string {
  return s.replace(/\|/g, '\\|').replace(/\r?\n/g, '<br>');
}
