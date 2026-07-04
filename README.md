# Vortex — Enterprise LLM Gateway

Multi-tenant (SaaS) or self-hosted (on-prem) OpenAI/Anthropic-compatible LLM gateway with
enterprise governance: per-member budgets, RBAC, audit, cost attribution.

> Full spec: `.claude/plans/2026-07-04-vortex-llm-gateway.md`

## Stack
- **API + gateway**: Hono (`@hono/node-server`, tsx) — `apps/api`
- **Tenant console**: Angular 22 (zoneless SPA) + `@kouji-ui` — `apps/web`
- **Platform console** (SaaS super-admin): Angular 22 — `apps/platform`
- **DB**: Postgres + Drizzle (+ RLS) — `packages/db`
- **Shared**: Zod DTOs — `packages/shared`
- **Core services**: `packages/core` · **CLI**: `packages/cli`
- **Cache/counters**: Redis · **Billing**: Stripe (SaaS only)

## Local dev
```bash
pnpm install
cp .env.example .env         # fill secrets
pnpm db:up                   # Postgres + Redis (docker)
pnpm db:migrate && pnpm db:seed
pnpm dev:api                 # http://localhost:8080
pnpm dev:web                 # http://localhost:4200
```

## Layout (feature-per-folder + hexagonal-lite)
```
apps/
  api/        Hono API + gateway (features/*: router → service → db)
  web/        Angular tenant console
  platform/   Angular platform (super-admin) console
packages/
  db/         Drizzle schema + migrations + RLS
  shared/     Zod DTOs shared across apps
  core/       provider registry, gateway core, services
  sdk/        thin client + acting-user/acting-app helpers
  cli/        Vortex CLI
```
