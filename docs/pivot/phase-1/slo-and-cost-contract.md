# Phase 1 — SLO & Cost Contract

## 1. Purpose

Cross-cutting contract. Pins latency budget, infra unit economics, pricing tiers, gross margin. Without these numbers VC cannot underwrite, design partner cannot sign, platform eng cannot size hardware.

## 2. Latency Budget

Gateway overhead only. Excludes provider token generation. Measured at the gateway egress vs ingress, non-streaming first-byte.

| Component | p50 (ms) | p99 (ms) | Notes |
|---|---|---|---|
| Auth (key lookup, hashed, Redis) | 1 | 3 | Cached key → org/policy |
| Rate-limit (token bucket, Redis Lua) | 1 | 3 | Per-key + per-org |
| Policy resolve (model allow, redact rules) | 2 | 5 | In-memory, hot-reload |
| Guardrail (regex PII, injection patterns) | 3 | 8 | Pre-flight only |
| Cache lookup (prompt hash → response) | 2 | 6 | Redis GET, semantic off |
| Audit hash + enqueue (async) | 1 | 4 | Hash sync, write async |
| Provider call (network only, first byte) | 30 | 250 | Anthropic / OpenAI EU |
| Audit commit (Postgres, async) | 0 | 0 | Off critical path |
| **Total gateway overhead** | **10** | **30** | Excludes provider |
| **Total end-to-end (p99)** | **40** | **280** | Includes provider |

SLO commitment: **gateway overhead p99 < 30 ms** at 100 QPS sustained.

## 3. Throughput Targets

Per node = 4 vCPU / 8 GB. Async Python (uvicorn + uvloop) or Rust proxy if needed.

| Metric | Target |
|---|---|
| Concurrent streaming connections / node | 2,000 |
| Sustained QPS / node at p99 < 100 ms | 500 |
| Burst QPS / node (10s) | 1,500 |
| Horizontal scale | Linear to 10 nodes, Redis = bottleneck after |

## 4. Infra Cost Model

Design partner scale: 50M tokens/month proxied. EU region (Frankfurt). Self-managed K8s or Hetzner / Scaleway.

| Component | €/month | €/1M tok |
|---|---|---|
| Compute (3× 4vCPU node, HA) | 180 | 3.60 |
| Postgres (HA pair, 200 GB audit) | 220 | 4.40 |
| Redis (HA, 8 GB) | 80 | 1.60 |
| Observability (Loki + Prom + Tempo, self-host) | 90 | 1.80 |
| Egress (mostly intra-region, <5%) | 30 | 0.60 |
| **Total infra COGS** | **600** | **12** |

Provider tokens **pass-through**, billed at customer's contract (or markup, see §6).

## 5. Pricing Tiers

Indicative annual, EU bank / large enterprise. Token spend extra unless flat-rate add-on.

| Tier | Price/yr | Gating |
|---|---|---|
| Starter | €50k | OpenAI-compat API, keys, rate-limit, basic audit, 1 provider, no SSO, community support |
| Growth | €120k | + multi-provider, guardrails, RBAC, dashboard, SLA 99.5%, business-hours support |
| Enterprise | €300k+ | + SSO (SAML/Entra), self-hosted Helm, signed audit log, SLA 99.9%, 24/7, named CSM, on-prem provider |

Below Starter: not Phase 1 ICP. No SaaS sub-€20k tier.

## 6. Gross Margin

Target **75%+ at Enterprise**. Per-customer math (Enterprise, 50M tok/mo, €300k/yr):

- Revenue: €300,000
- Infra COGS: €7,200 (€600 × 12)
- Support + CSM allocation: €60,000
- **Gross margin: 77.6%**

Sensitivity:
- Pass-through provider tokens → margin protected, no inventory risk.
- Markup mode (10% on tokens, 50M tok @ €5/M avg = €250/mo extra): margin **+0.8 pt**, adds billing risk.
- Default: **pass-through**. Markup opt-in at Growth+ for managed-billing convenience.

## 7. Out of Scope — Phase 1

- Multi-region active-active. Single EU region only.
- Sub-10 ms p99 gateway overhead. Not needed for chat/agent traffic.
- Sub-€20k/yr self-serve SaaS tier. Distraction from ICP.
- Custom-VPC dedicated tenancy below Enterprise.
- GPU inference hosting (we proxy, we do not serve weights).

## 8. Done When

- Load test signed: p99 gateway overhead < 30 ms at 500 QPS / node, 30 min sustained.
- One design partner in prod within a tier band (Starter–Enterprise).
- Cost dashboard shows €/1M tok proxied matches model ± 15%.
- Gross margin reported monthly, ≥ 75% on Enterprise contracts.
