# Observability

## 1. Purpose
Real-time ops telemetry for LLM traffic: latency, errors, throughput, per-key/model breakdowns. Export to bank's existing stack (Datadog/Grafana/Splunk).

## 2. Buyer pain
- CISO/RSSI: "When GPT-4 hangs at 3am, who pages? Where's the trace?"
- Platform Eng: "I have Datadog. Don't sell me another dashboard. Export OTLP or go home."
- Today: gateway is a black box. Outages diagnosed by tailing logs.

## 3. Sub-features
- [must-have] OpenTelemetry traces (OTLP/HTTP export) — spans per request: route -> provider -> tokens -> cost (table stakes for bank ingest)
- [must-have] OTel `gen_ai.*` semantic conventions + version pin (standard schema or Datadog won't ingest)
- [must-have] PII scrubbing in spans/logs (prompts in traces leak same data audit-log redacts; GDPR)
- [must-have] Prometheus `/metrics` endpoint — RED metrics labelled by `key_id`, `model`, `provider`, `route` (every bank scrapes Prom)
- [must-have] Structured JSON logs to stdout — `trace_id`, `org_id`, `key_id`, `model`, `status`, `latency_ms` (SIEM ingest)
- [must-have] p50/p95/p99 latency histograms per model+provider (SLO reporting)
- [must-have] Error taxonomy — `provider_5xx`, `rate_limit`, `timeout`, `policy_block`, `auth_fail` (paging signal)
- [nice-to-have] Trace sampling config, head + tail on errors (cost control, not blocker)
- [nice-to-have] Minimal built-in Ops view: live req/s, error %, p95 (demos only)
- [skip] Custom dashboards / alerting UI (banks use Grafana/Datadog)
- [skip] Log storage / search backend (ship to their SIEM)
- [skip] APM-style flamegraphs (Datadog APM owns this)

## 4. Actionable tasks
1. Add `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, `prometheus-client` to `server/api/pyproject.toml`
2. Create `server/api/src/ai_portal/observability/tracing.py` — init tracer, OTLP exporter, env-driven endpoint (`OTEL_EXPORTER_OTLP_ENDPOINT`)
3. Create `server/api/src/ai_portal/observability/metrics.py` — Prom registry, `http_requests_total`, `llm_request_duration_seconds`, `llm_tokens_total`
4. FastAPI middleware in `main.py` — wrap each request in span, emit metrics on completion
5. Instrument `chat/streaming/orchestrator.py` — span per provider call with `gen_ai.*` semantic conventions
6. Instrument `catalog/providers/*.py` — child span per upstream HTTP call, status/latency
7. PII scrubber hook on span exporter — strip message bodies, allowlist attributes
8. Expose `GET /metrics` and `GET /healthz`; gate `/metrics` behind internal-network ACL
9. Switch logging to `structlog` JSON; inject `trace_id` via contextvar
10. Add `docs/ops/observability.md` — env vars, Grafana JSON, Datadog OTLP config
11. E2E: `observability.spec.ts` — assert `/metrics` returns Prom format, trace headers propagate

## 5. Competitive note
Portkey + LiteLLM ship dashboards but weak OTLP. Cloudflare AI Gateway = closed SaaS, no self-host export. Our edge: native OTLP + Prom, no lock-in, runs in their VPC.

## 6. Risks
- OTel Python SDK churn — pin versions, wrap in adapter
- OTel `gen_ai.*` conventions still draft — field names shift, re-map on bump
- Cardinality explosion: per-`key_id` + per-`model` labels blow up Prom — cap labels, use exemplars
- PII in span attributes (prompts) — strict allowlist; scrubber on export
- SIEM/APM integration matrix unbounded — each bank runs different stack (Datadog/Splunk/Dynatrace/Elastic); scope to OTLP + Prom, refuse custom adapters

## 7. Done-when
Demo: curl gateway, trace visible in buyer's Grafana Tempo / Datadog within 60s. `/metrics` scraped, p95 panel per model.
