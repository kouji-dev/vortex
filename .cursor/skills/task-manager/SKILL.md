---
name: task-manager
description: Task manager for scopes, EPICs, and tickets in SQLite via a local Hono MCP server—assignee locks for parallel agents, Markdown export. Pairs with Superpowers (brainstorming, writing-plans, dispatching-parallel-agents, using-git-worktrees). Use when planning or executing independent EPICs with isolated agents and one in-repo source of truth.
---

# Task manager

## What it is

- **SQLite** (`better-sqlite3`): **scopes**, **EPICs**, and **tickets**; default DB `scripts/epic-ticket-server/data/epic-tickets.db` (`EPIC_TICKET_DB` overrides).
- **MCP**: Node + **Hono**, Streamable HTTP at **`/mcp`** (see [reference/mcp.md](reference/mcp.md) for tools).

**Run:** `cd .cursor/skills/task-manager/scripts/epic-ticket-server` → `npm install` → `npm start`. **`MCP_PORT`** default `3847`; health `GET /health`; MCP `http://localhost:<port>/mcp`.

### Cursor (this repo)

- **Project MCP config:** [`.cursor/mcp.json`](../../mcp.json) registers **`task-manager`** as a **Streamable HTTP** server at `http://localhost:3847/mcp` (same default as `MCP_PORT`).
- **After pulling changes:** restart Cursor (or reload MCP) so the server appears under **Settings → MCP** / **Available Tools**.
- **Before using tools:** the Node server must be running (`npm start`). If you change `MCP_PORT` when starting the server, update the `url` in `.cursor/mcp.json` to match (or use Cursor’s global `mcp.json` with a different URL).
- **Board data:** create scopes/EPICs/tickets with MCP tools—no separate seed script. Existing databases get a **Default** scope and all prior EPICs are linked to it on first startup after upgrade.

## Model (short)

Hierarchy: **Scope → EPIC → ticket**.

- **Scope / EPIC / ticket:** `title`, `description`, `status` — `backlog` | `ready` | `in_progress` | `blocked` | `done` | `cancelled`.
- **EPIC** also has **`scope_id`** (which scope it belongs to).
- **Ticket:** `epic_id`, `agent` (owner label), `idea` (intent), **`locked`** (0/1). Set **`agent`** before locking.
- **Lock:** `set_ticket_lock` (`locked`, `actor` = assignee). While locked, **`update_ticket` / `delete_ticket` need `actor` matching `agent`** (case-insensitive); everyone else uses **`list_*` / `export_board_markdown`** only. SQLite does not enforce product rules—the server does.

## Tools (summary)

| Tool | Role |
| --- | --- |
| `list_scopes`, `create_scope`, `update_scope`, `delete_scope` | Scope CRUD (`delete` cascades EPICs and tickets). **`list_scopes`**: optional **`status`** filter. |
| `list_epics`, `create_epic`, `update_epic`, `delete_epic` | EPIC CRUD. **`list_epics`**: optional **`scope_id`**, **`status`** (AND). |
| `list_tickets`, `create_ticket`, `update_ticket`, `delete_ticket` | Ticket CRUD; **`list_tickets`**: optional **`epic_id`**, **`status`**, **`locked`**, **`agent`** (AND). **`actor`** on update/delete when locked |
| `set_ticket_lock` | Assignee locks/unlocks |
| `export_board_markdown` | Read-only board snapshot (optional **`scope_id`** or **`epic_id`**) |

Details and examples: [reference/mcp.md](reference/mcp.md).

## Recommended flow (Superpowers + board + parallel agents)

**Before parallel work (steps 5+):** **brainstorming** (step 2) and **writing-plans** (step 3) should **prefer and actively pursue independent EPICs**—features that can ship with minimal shared mutable state and clear interfaces—so **each EPIC can be worked in parallel** when possible. Group related EPICs under a **scope** (product area or MVP phase) so the board stays navigable.

1. **Task manager server** — **Start and verify** the MCP server before anything else that uses the board: run `npm start` from `scripts/epic-ticket-server`, confirm **`GET /health`** (or that the client’s MCP connection to `http://localhost:<port>/mcp` works). Do not proceed to board sync until tools are reachable.
2. **brainstorming** — Shape requirements; define **scopes** (domains) and **EPICs** (one shippable slice per EPIC where possible).
3. **writing-plans** — After approval, **one implementation plan per EPIC**, with dependencies called out so parallel EPICs stay runnable in parallel.
4. **Sync the board** — `create_scope` (if needed) → `create_epic` (set **`scope_id`**) → `create_ticket`; align **`agent`** + **`idea`** with the plan.
5. **Parallel execution** — Where EPICs are independent, run them **in parallel**: **using-git-worktrees** (isolated branch/worktree; ensure project-local worktrees are gitignored) and **dispatching-parallel-agents** (each agent gets only its ticket + paths, not full chat history).
6. **Locks** — When an assignee is actively working a ticket, **`set_ticket_lock`** (`locked: true`, `actor` = that **`agent`**). Other agents **read** via `list_tickets` / `export_board_markdown`; only the assignee mutates until **`set_ticket_lock`** (`locked: false`).
7. **Ship** — Update statuses; unlock or delete tickets as work completes.

## Ralph delivery loop (project habit)

This repo uses an **always-on Cursor rule**: [`.cursor/rules/ralph-delivery-loop.mdc`](../../rules/ralph-delivery-loop.mdc). Agents should default to that cycle: **list board → pick ticket → implement → run CI-aligned checks → `update_ticket` → repeat**, using the MCP tools above. Pair with **using-git-worktrees** and **dispatching-parallel-agents** when work is parallelizable.

## Agent behavior

- **Confirm the server is up** (step 1) before calling board tools; if unreachable, start it or tell the user to start it.
- Use **MCP tools** for the board; do not maintain a second tracker.
- Treat locked tickets as **assignee-write, others-read**; pass **`actor`** on mutating calls when **`locked`** is set.
- Prefer the **Ralph loop** rule for day-to-day execution cadence.
