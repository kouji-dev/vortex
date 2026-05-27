# Phase 1 Compliance Matrix

## 1. Purpose
Map EU AI Act / DORA / GDPR articles to Phase 1 gateway features and the exact audit artifact that proves compliance. One doc the CISO/DPO hands to procurement.

## 2. EU AI Act

| Article | Requirement | Phase 1 feature(s) | Audit artifact (exportable) |
|---|---|---|---|
| Art. 9 — Risk management | Continuous risk assessment over lifecycle | Guardrails, Policies & RBAC, CISO Dashboard (blocked-req feed, policy violations) | Policy decision log (JSONL); blocked-requests CSV; risk-indicator panel PNG |
| Art. 10 — Data governance | Quality + provenance of input data | Guardrails (PII redaction, EU regex pack), Audit Log (prompt SHA-256), Policies (region allowlist) | Redacted prompt/response with hashes; regex hit-list; per-org `audit_full_capture` setting |
| Art. 11 — Technical documentation | System docs available to authorities | Self-Hosted Deploy (`docs/security/data-flow.md`, runbook, RPO/RTO), Multi-Provider Routing (schema-family tags) | Data-flow diagram; Helm values; model catalog with provider/region tags |
| Art. 12 — Record-keeping (logs) | Automatic event logging over lifecycle | Audit Log (hash-chained, append-only Postgres trigger), Observability (OTel `gen_ai.*`) | `audit_events` JSONL export with `prev_hash`/`row_hash`; chain-verify script output |
| Art. 13 — Transparency | Inform users of AI interaction + limits | OpenAI/Provider-Compatible API (model id surfaced), Audit Log (model_id per row) | Per-call model attribution row; `/v1/models` catalog response |
| Art. 14 — Human oversight | Human can intervene/override | Policies & RBAC (deny-default, kill-switch), API Key Management (revoke), Rate Limiting (admin override) | Key lifecycle events log (`key.created/rotated/revoked/used`); policy version history |
| Art. 15 — Accuracy + robustness + cybersecurity | Technical controls, resilience | Guardrails (prompt-injection heuristics, secrets detection), Multi-Provider Routing (circuit breaker, failover), Observability (RED metrics, p50/p95/p99) | Guardrail event feed; routing decision rows with `reason=primary_5xx`; Prom metrics scrape |
| Art. 16-17 — Quality management | Provider QMS + post-market monitoring | CISO Dashboard, Observability, Audit Log retention (7yr WORM sink nice-to-have) | Dashboard PNG export; OTLP traces in customer SIEM; archived audit bundle |

Partial: Art. 9 risk register and Art. 17 post-market monitoring are evidence-only — no formal QMS workflow in Phase 1.

## 3. DORA

| Pillar (Reg. 2022/2554) | Requirement | Phase 1 feature(s) | Audit artifact (exportable) |
|---|---|---|---|
| Art. 5-15 — ICT risk management | Identify/protect/detect/respond on ICT assets | Policies & RBAC, Guardrails, Self-Hosted Deploy (VPC, no egress), SSO + MFA pass-through | Policy CRUD log; SSO config + group-role map; data-flow diagram |
| Art. 17-23 — Incident reporting | Classify + report major ICT incidents | Audit Log, Observability (error taxonomy: `provider_5xx`, `rate_limit`, `policy_block`), CISO Dashboard (blocked-req feed) | Incident timeline from audit JSONL filtered by `error_class`; OTel traces |
| Art. 28-30 — Third-party risk | Concentration + exit strategy on ICT providers | Multi-Provider Routing + Failover (Anthropic/OpenAI/Gemini/Mistral on-prem/Bedrock), Policies (region allowlist) | Provider mix donut; routing decision audit rows proving failover; sovereign-EU route evidence |
| Art. 24-27 — Resilience testing | Threat-led + scenario testing | Multi-Provider Routing (circuit breaker, schema-family snapshot tests), Rate Limiting (fail-closed/open modes) | Failover E2E test report; rate-limit 429 traces; chaos scenario log |

Partial: TLPT (threat-led pen-test) is customer-side; we expose hooks (kill-switch, mock-primary mode) but do not run it.

## 4. GDPR

| Article | Requirement | Phase 1 feature(s) | Audit artifact (exportable) |
|---|---|---|---|
| Art. 5 — Purpose limitation, minimisation | Process only what is needed | Audit Log (`audit_full_capture` OFF by default, SHA-256 only), Guardrails (PII redaction inbound) | Org setting screenshot; redacted prompt rows with hashes |
| Art. 17 — Right to erasure | Delete on data-subject request | Audit Log (per-user filter), API Key Management (key revoke + audit) | User-scoped audit export + delete script; key lifecycle row |
| Art. 25 — Privacy by design | Default-secure config | Guardrails (regex pack ON by default), Policies (deny-default mode), Self-Hosted Deploy (EU-only ingress) | Default policy YAML; deploy config diff; cache namespace test proving tenant isolation |
| Art. 30 — Records of processing | Actor + purpose + recipient trail | Audit Log (actor chain: user→key→route→provider), Policies (region allowlist proof) | Actor-chain JSONL; provider/region per row |
| Art. 32 — Security of processing | Encryption, access control, resilience | SSO (SAML + MFA pass-through), API Key Management (HMAC + pepper, expiry, rotation), Rate Limiting | Key hash config; SSO assertion log; 429/concurrency E2E result |
| Art. 33 — Breach notification | Detect + report within 72h | Audit Log (tamper-evident), Observability (SIEM webhook), CISO Dashboard (real-time blocked feed) | Hash-chain verify output proving no silent mutation; SIEM ingest sample |

Partial: full DPIA template is buyer-side; we ship the evidence inputs, not the DPIA doc.

## 5. ISO 27001 / SOC 2 alignment
Today we cover access control (A.9 / CC6), logging (A.12.4 / CC7.2), change mgmt for the gateway itself (A.12.1 / CC8.1), and supplier mgmt via provider routing (A.15 / CC9.2). Phase 2 ask: formal control narratives, SOC 2 Type II audit window, signed SBOM/Cosign provenance, FIPS image variant. Phase 1 ships the evidence; the certification engagement is the customer's contract with their auditor.

## 6. Gaps acknowledged
Phase 1 does NOT cover:
- Model risk lifecycle mgmt (SR 11-7 / EBA model governance) — no model approval workflow, no challenger tracking.
- Red-team / TLPT pen-test program — hooks exist, program does not.
- Formal DPIA template — evidence inputs only.
- Bias / fairness testing — out of scope until Phase 3.
- Continuous post-market monitoring workflow — telemetry yes, formal QMS no.
- Signed SBOM + SLSA provenance — design-partner-triggered, not default.

## 7. Done-when
Single artifact pack exported from gateway admin UI: ZIP containing audit JSONL (hash-verified), policy YAML snapshot, key lifecycle log, routing-decision log, guardrail event feed, dashboard PNG, data-flow diagram, runbook. Each control above maps to one file in the pack. CISO drops it on the regulator's desk.
