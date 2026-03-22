# Task manager — MCP tools reference

The **task-manager** MCP server exposes **tools** (not resources) over **Streamable HTTP**. Connect the client to the server’s MCP endpoint (see [SKILL.md](../SKILL.md) for run instructions).

- **Server name / version:** `task-manager` / `0.5.0`
- **Default base URL:** `http://localhost:3847` (override with `MCP_PORT`)
- **MCP path:** `/mcp`
- **Health:** `GET /health`

## Response shape

All tools return **text** content:

- Most tools: **pretty-printed JSON** (object or array) as a single text block.
- `export_board_markdown`: **Markdown** string (nested: **Scope → EPIC → tickets**).
- Failures: text starting with `Error: …` (validation, not found, or lock / assignee rules).

## Shared fields

### Status (`status`)

Allowed values for **scopes**, **EPICs**, and **tickets**:

`backlog` · `ready` · `in_progress` · `blocked` · `done` · `cancelled`

### List filters (`filters` on `list_scopes`, `list_epics`, `list_tickets`)

Optional **`filters`** is a JSON object: **keys = column names** (allowlisted per tool); **values** combine into SQL with **AND**; all values are **bound as parameters** (no raw SQL injection).

| Value shape | SQL |
| --- | --- |
| scalar (string / number / boolean where allowed) | `column = ?` |
| non-empty array | `column IN (?, …)` |
| `{ "in": [ … ] }` | same as array |
| `{ "like": "%foo%" }` | `column LIKE ? ESCAPE '\'` (SQLite `LIKE` is ASCII case-insensitive by default) |
| `null` | `column IS NULL` |

**Allowlisted columns**

- **`list_scopes`:** `id`, `title`, `description`, `status`, `created_at`, `updated_at`
- **`list_epics`:** `id`, `scope_id`, `title`, `description`, `status`, `created_at`, `updated_at`
- **`list_tickets`:** `id`, `epic_id`, `title`, `description`, `status`, `agent`, `idea`, `locked`, `created_at`, `updated_at`

**Notes:** `status` values are validated against [Status](#status-status). Integer columns (`id`, `scope_id`, `epic_id`) must be integers. **`locked`** accepts `true` / `false` or `0` / `1`. Omit **`filters`** or pass `{}` to list all rows.

### Ticket lock (`locked`)

Stored as `0` or `1` on each ticket row.

- **`set_ticket_lock`** sets `locked`; only the **assigned agent** (`agent` on the ticket) may call it, and **`agent` must be set** before locking.
- When **`locked` is 1**, **`update_ticket`** and **`delete_ticket`** require **`actor`** to match **`agent`** (trimmed, case-insensitive). Other callers should use read-only tools (`list_*`, `export_board_markdown`).
- When **`locked` is 0**, `actor` is optional for update/delete.

---

## Tools

### `list_scopes`

Returns scopes (JSON array). Omit filters to list all.

| Argument | Type | Required | Notes |
| --- | --- | --- | --- |
| `status` | string | no | One of [Status](#status-status) values. |

---

### `create_scope`

Creates one scope (domain / bucket for EPICs).

| Argument | Type | Required | Notes |
| --- | --- | --- | --- |
| `title` | string | yes | Non-empty. |
| `description` | string | no | |
| `status` | string | no | Defaults to `backlog` if omitted. |

---

### `update_scope`

Patches a scope by `id`.

| Argument | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | number | yes | Positive integer. |
| `title` | string | no | Non-empty if provided. |
| `description` | string \| null | no | |
| `status` | string | no | |

---

### `delete_scope`

Deletes a scope and **all EPICs in that scope and their tickets** (SQLite foreign-key cascade).

| Argument | Type | Required |
| --- | --- | --- |
| `id` | number | yes |

---

### `list_epics`

Returns EPICs (JSON array). Each row includes **`scope_id`**.

| Argument | Type | Required | Notes |
| --- | --- | --- | --- |
| `filters` | object | no | [List filters](#list-filters-filters-on-list_scopes-list_epics-list_tickets); keys must be epic columns. |

---

### `create_epic`

Creates one EPIC under a scope.

| Argument | Type | Required | Notes |
| --- | --- | --- | --- |
| `scope_id` | number | no | If omitted, uses the **first** scope by id (often the auto-created **Default** scope). |
| `title` | string | yes | Non-empty. |
| `description` | string | no | |
| `status` | string | no | Defaults to `backlog` if omitted. |

---

### `update_epic`

Patches an EPIC by `id`.

| Argument | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | number | yes | Positive integer. |
| `scope_id` | number | no | Move EPIC to another scope. |
| `title` | string | no | Non-empty if provided. |
| `description` | string \| null | no | |
| `status` | string | no | |

---

### `delete_epic`

Deletes an EPIC and **all of its tickets** (SQLite CASCADE).

| Argument | Type | Required |
| --- | --- | --- |
| `id` | number | yes |

---

### `list_tickets`

Lists tickets.

| Argument | Type | Required | Notes |
| --- | --- | --- | --- |
| `filters` | object | no | [List filters](#list-filters-filters-on-list_scopes-list_epics-list_tickets); keys must be ticket columns. Example: `{ "epic_id": 1 }`, `{ "status": "in_progress" }`, `{ "agent": { "like": "%auth%" } }`, `{ "locked": true }`. |

---

### `create_ticket`

Creates a ticket under an EPIC.

| Argument | Type | Required | Notes |
| --- | --- | --- | --- |
| `epic_id` | number | yes | Must reference an existing EPIC. |
| `title` | string | yes | Non-empty. |
| `description` | string | no | |
| `status` | string | no | Defaults to `backlog`. |
| `agent` | string | no | Assignee label for locking / ownership. |
| `idea` | string | no | Short intent for the assignee. |

New tickets are created with **`locked` = 0**.

---

### `update_ticket`

Patches a ticket. Respects **lock** rules (see [Shared fields](#shared-fields)).

| Argument | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | number | yes | |
| `actor` | string | no | **Required** when the ticket is **locked**; must match `agent`. |
| `epic_id` | number | no | Move ticket to another EPIC. |
| `title` | string | no | Non-empty if provided. |
| `description` | string \| null | no | |
| `status` | string | no | |
| `agent` | string \| null | no | |
| `idea` | string \| null | no | |

---

### `delete_ticket`

Deletes a ticket. Respects **lock** rules.

| Argument | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | number | yes | |
| `actor` | string | no | **Required** when the ticket is **locked**; must match `agent`. |

---

### `set_ticket_lock`

Sets **`locked`** to `true` or `false`. Only the **assigned agent** may call this; **`agent` must be set** on the ticket before locking.

| Argument | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | number | yes | Ticket id. |
| `locked` | boolean | yes | `true` to restrict updates/deletes to assignee; `false` to lift restriction. |
| `actor` | string | yes | Must match the ticket’s `agent`. |

---

### `export_board_markdown`

Renders **scopes**, **EPICs**, and **tickets** as **Markdown** (per-scope sections, EPIC subsections, tables + ticket detail). Read-only.

| Argument | Type | Required | Notes |
| --- | --- | --- | --- |
| `epic_id` | number | no | If set, only that EPIC (and its scope header). |
| `scope_id` | number | no | If set, only that scope’s EPICs and tickets. |

Do **not** pass both `epic_id` and `scope_id`.

---

## Example argument shapes (for clients)

```json
{ "title": "Guardrails", "description": "GR-01–GR-06 delivery", "status": "ready" }
```

```json
{ "scope_id": 1, "title": "MVP-3 Chat & assistants", "status": "in_progress" }
```

```json
{ "epic_id": 1, "title": "Implement OAuth callback", "agent": "agent-auth", "idea": "Hono route + cookie" }
```

```json
{ "id": 3, "locked": true, "actor": "agent-auth" }
```

```json
{ "id": 3, "status": "done", "actor": "agent-auth" }
```

```json
{ "filters": { "scope_id": 2 } }
```

```json
{ "filters": { "epic_id": 1, "status": ["backlog", "ready"] } }
```

```json
{ "filters": { "title": { "like": "%OAuth%" } } }
```

(Exact invocation depends on your MCP client: tool name + JSON arguments.)
