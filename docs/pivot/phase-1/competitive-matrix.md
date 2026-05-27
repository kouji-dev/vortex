# Phase 1 Competitive Matrix

## 1. Purpose
Score Phase 1 (0-6mo) feature scope against incumbent AI gateways for the EU-regulated CISO buyer. Drives RFP positioning, wedge selection, and threat triage.

## 2. Feature matrix

Legend: Y = shipping / GA, P = partial / limited, N = not shipped, E = enterprise-tier only, R = roadmap-stated.
Columns: Portkey OSS (PK-OSS), Portkey Enterprise (PK-E), LiteLLM OSS (LL-OSS), LiteLLM Enterprise (LL-E), Cloudflare AI Gateway (CF), Vercel AI Gateway (VC), Azure AI Foundry (AZ), Us Phase 1 (Us).

| Feature | PK-OSS | PK-E | LL-OSS | LL-E | CF | VC | AZ | Us |
|---|---|---|---|---|---|---|---|---|
| OpenAI `/v1/chat/completions` compat | Y | Y | Y | Y | Y | Y | P | Y |
| Anthropic `/v1/messages` native compat | P | Y | P | P | P | P | N | Y |
| Bedrock Converse compat | N | P | P | P | N | N | N | Y |
| Multi-provider routing | Y | Y | Y | Y | Y | Y | P | Y |
| Failover chain w/ schema-family guard | Y | Y | Y | Y | P | P | N | Y |
| Pre-flight cost reserve (HTTP 402) | N | P | P | Y | N | N | N | Y |
| Per-key budget cap | P | Y | Y | Y | N | Y | P | Y |
| Per-team budget cap + chargeback CSV/PDF | N | Y | P | Y | N | P | P | Y |
| Rate limit QPS per key | Y | Y | Y | Y | P | P | Y | Y |
| Rate limit TPM with pre-reserve+refund | P | P | P | Y | N | N | P | Y |
| Concurrent-stream cap | N | P | P | P | N | N | N | Y |
| Audit log (gateway calls) | P | Y | P | Y | P | P | Y | Y |
| Hash-chain tamper-evidence (DB-level append-only) | N | N | N | N | N | N | N | Y |
| Body-capture redaction (per-org toggle) | P | Y | P | Y | N | N | P | Y |
| PII redaction inbound/outbound | P | Y | P | Y | P | N | P | Y |
| EU-format PII (IBAN, NIR, SIREN) | N | N | N | N | N | N | N | Y |
| Prompt-injection heuristics | Y | Y | P | Y | N | N | P | Y |
| Output validation / schema | P | Y | P | Y | N | N | P | N |
| Pluggable ML guardrails (Lakera/Presidio) | Y | Y | N | P | N | N | P | Y |
| Prompt caching passthrough | Y | Y | P | Y | Y | P | P | Y |
| Exact-match gateway cache w/ tenant namespace | Y | Y | Y | Y | Y | N | N | Y |
| Semantic cache | Y | Y | P | Y | N | N | N | N |
| RBAC + hierarchical scopes | P | Y | P | Y | P | P | Y | Y |
| Region/residency policy (EU-only enforce) | N | P | N | P | N | N | P | Y |
| Observability OTel `gen_ai.*` semconv | P | Y | P | Y | N | P | Y | Y |
| Prometheus `/metrics` | P | Y | Y | Y | N | N | P | Y |
| SIEM webhook (Splunk/Sentinel/Elastic) | N | Y | N | Y | N | N | Y | P |
| SSO SAML 2.0 (generic, per-org IdP) | N | Y | N | Y | N | N | Y | Y |
| Entra/OIDC SSO | N | Y | P | Y | N | P | Y | Y |
| SCIM 2.0 provisioning | N | Y | N | P | N | N | Y | Y |
| Helm chart | N | Y | Y | Y | N | N | Y | Y |
| Self-host on-prem / customer VPC | Y | Y | Y | Y | N | N | P | Y |
| Air-gapped install (offline bundle) | N | P | N | P | N | N | P | Y |
| OpenShift / Rancher variant | N | P | N | P | N | N | P | R |
| KMS/HSM key wrap | N | Y | N | P | N | N | Y | R |
| Machine identity (OIDC workload tokens) | N | P | N | P | N | N | Y | Y |
| CISO dashboard (security-first, AI Act framed) | N | N | N | N | N | N | P | Y |

## 3. Five wedges (Us > all competitors for EU bank CISO)

- EU-sovereign self-host + Mistral-on-prem first-class provider — CF/VC have no on-prem; PK/LL self-host but no Mistral-native EU framing.
- DORA-grade audit: sync hash-chain + Postgres-trigger append-only + per-org redaction toggle — nobody ships DB-level tamper-evidence.
- EU-regex guardrail pack (IBAN mod-97, NIR+key, SIREN, FR phone, PAN Luhn) — incumbents ship US-PII only.
- Three native wire formats day-one (OpenAI + Anthropic Messages + Bedrock Converse) governed by one control plane — PK/LL are OpenAI-first with thin Anthropic shims.
- CISO-first dashboard mapped to EU AI Act Art. 12/15/26 + DORA — incumbents lead with dev/ops dashboards.

## 4. Two threats (Us < competitors today)

- Semantic cache: Portkey + LiteLLM ship it as headline feature; we explicitly skipped (banking liability) — RFP scoring tables will mark a gap.
- SIEM-native webhook + KMS/HSM + OpenShift: PK-E and Azure ship these GA today; we have partial SIEM and KMS/OCP on roadmap — large-bank procurement may block.

## 5. Pricing posture

PK-E + LL-E + Azure price per-call or per-seat with enterprise floors (USD 30-60k/yr typical entry). CF/VC bundle into platform spend, no per-tenant control. Us: self-host flat-fee per cluster + optional EU support tier — sells against per-call meter on bank's high-volume traffic, undercuts PK-E on TCO at >5M calls/month, and removes the SaaS-residency objection that kills CF/VC in EU procurement.

## 6. Done-when

This matrix backs a winning RFP when:
- Bank security questionnaire (SIG-Lite / DORA Annex) maps 1:1 to a Y cell with file pointer to the Phase 1 spec.
- Five wedges show as differentiators in a side-by-side slide and survive design-partner challenge.
- Both threats have a documented Phase 2 close date or a contractual carve-out.
- Sales loses zero deal on a feature scored Y here; loss post-mortems update the matrix within one week.

Sources:
- [Portkey enterprise gateway](https://portkey.ai/features/ai-gateway)
- [Portkey SSO docs](https://portkey.ai/docs/product/enterprise-offering/org-management/sso)
- [LiteLLM enterprise features](https://docs.litellm.ai/docs/proxy/enterprise)
- [Cloudflare AI Gateway features](https://developers.cloudflare.com/ai-gateway/features/)
- [Cloudflare AI Gateway audit logs](https://developers.cloudflare.com/ai-gateway/reference/audit-logs/)
- [Vercel AI Gateway](https://vercel.com/docs/ai-gateway)
