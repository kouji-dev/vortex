# Git worktrees — Entra auth vs chat (merge order)

**Purpose:** Keep **epic 10** (Entra auth) and **epic 11** (conversations chat) shippable without cross-branch pain.

## Branches & paths

| Worktree path | Branch | Use for |
|---------------|--------|---------|
| Repo root (`ai-portal/`) | `main` (or your daily branch) | Integrate finished slices; CI truth |
| `.worktrees/entra-auth-mvp/` | `feat/entra-auth-mvp` | Finish **epic 10** tickets (JWT, `/api/me`, MSAL, docs, CI sweep) |
| `.worktrees/chat-post-auth/` | `feat/chat-post-auth-integration` | **Epic 11** — act as if Bearer + `GET /api/me` exist; **do not merge** until epic 10 is on `main` |

Create / refresh worktrees from repo root:

```bash
git worktree list
```

## Merge gate (required)

1. **Merge `feat/entra-auth-mvp` → `main` first** when **epic 10** is **done** (tickets 30–34, 39–40 as applicable). Board: `export_board_markdown` / task-manager MCP.
2. **Rebase** `feat/chat-post-auth-integration` onto updated `main`:

   ```bash
   cd .worktrees/chat-post-auth
   git fetch origin
   git rebase origin/main   # or main
   ```

3. **Then** implement or continue **epic 11** and open PR / merge `feat/chat-post-auth-integration` → `main`.

**Do not** merge the chat worktree into `main` before Entra auth is merged unless you enjoy duplicate auth commits and conflict resolution.

## Ralph loop reminder

On each session: `list_scopes` → `list_epics` → `list_tickets` (task-manager MCP) → pick **ready** / **in_progress** → verify with `ruff`, `pytest`, `npm run build` → `update_ticket` → repeat.

## Related docs

- Auth spec: `docs/superpowers/specs/2026-03-22-auth-entra-design.md`
- Auth plan: `docs/superpowers/plans/2026-03-22-auth-entra.md`
- Chat spec: `docs/superpowers/specs/2026-03-22-chat-conversations-design.md`
