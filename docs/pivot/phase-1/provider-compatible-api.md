# Provider-Compatible API

## Purpose
Speak three wire formats. One control plane. Dev tools point at our gateway, traffic governed end-to-end — no SDK rewrite, no proxy hack.

## Buyer pain (CISO/RSSI)
- Shadow AI: Claude Code hits `api.anthropic.com`, Cursor hits OpenAI, Bedrock apps hit AWS. Zero visibility.
- Multi-SDK lock-in: each tool wired to one vendor format. Cannot swap, cannot audit, cannot redact.
- Regulators ask "every prompt, every model, every user". Today: three blind spots.

## Sub-features
- [must-have] `POST /v1/chat/completions` (OpenAI) — Cursor, Continue, LangChain, custom
- [must-have] `POST /v1/messages` (Anthropic) — Claude Code, Anthropic SDK apps
- [must-have] `POST /model/{id}/converse` (Bedrock-Converse) — AWS-shop clients
- [must-have] `GET /v1/models` — unified catalog, all three surfaces
- [must-have] Bearer auth via portal API keys; per-key org scoping
- [must-have] Per-surface translator → internal `ChatProvider` events (reuse `catalog/providers/*`)
- [must-have] SSE streaming in each native format (OpenAI deltas, Anthropic event types, Converse stream)
- [must-have] Token + cost accounting per call (reuse `usage/consumption_service.py`)
- [must-have] Audit row per request (reuse `audit/service.py`)
- [nice-to-have] Cross-format routing (Claude Code → OpenAI model via Anthropic surface)
- [nice-to-have] Virtual model aliases (`bank-default` → real id)
- [nice-to-have] `/v1/embeddings` passthrough
- [skip] Assistants API, Files API, Batch, fine-tune, image gen, Bedrock InvokeModel legacy

## Actionable tasks
1. New module `server/api/src/ai_portal/gateway/` — three routers, shared auth/usage/audit hooks
2. `gateway/openai/` — schemas, translator, `POST /v1/chat/completions`, `GET /v1/models`
3. `gateway/anthropic/` — Messages schemas (incl. `cache_control`, `thinking`), translator, `POST /v1/messages`
4. `gateway/bedrock/` — Converse request/response, translator, `POST /model/{id}/converse` + `/converse-stream`
5. Per-surface translator: tool schema, stop reasons, JSON/structured-output, role mapping → internal event stream
6. Wire all three in `main.py` alongside `chat/router.py`; reuse `LlmProviderFactory.create()`
7. Golden-file tests per surface: `openai-python`, `anthropic-python`, `boto3.client('bedrock-runtime')`
8. E2E `apps/frontend/e2e/gateway-*.spec.ts` — one spec per surface, asserts stream + audit + usage row
9. Killer-demo script: real Claude Code session → `ANTHROPIC_BASE_URL=https://portal` → audited, redacted, billed

## Competitive note
Portkey/LiteLLM/Cloudflare AI Gateway = SaaS, US-hosted, OpenAI-format only or thin Anthropic shim. We ship self-hosted EU VPC with all three native surfaces day one.

## Risks
- Vendor schema drift — Anthropic adds caching/thinking params, OpenAI rewrites tool format, Bedrock adds fields. Subscribe to changelogs; weekly contract-test job against live SDKs.
- Cross-schema semantics differ — tool-call shape, stop reasons, JSON mode, system-prompt placement. Wrong translation = silent breakage in customer code. Fix: golden tests + property tests per surface.
- Streaming event mismatch — Anthropic `message_delta` vs OpenAI `chunk.delta` vs Converse `contentBlockDelta`. Per-surface SSE serializer, never share.
- Liability creep — customers blame us for upstream provider bugs. Pass-through error envelope with `x-portal-upstream-error: true`.

## Done-when
Dev runs unmodified Claude Code with `ANTHROPIC_BASE_URL=https://portal` AND unmodified Cursor with `OPENAI_BASE_URL=https://portal/v1` AND a `boto3` Converse client against `https://portal` — all three calls land in the same admin console, same audit log, same budget, within 2 s.
