# Self-Hosted Deploy

## 1. Purpose
Ship a production-grade install of the gateway inside the bank's VPC in under one day. Zero data egress to vendor.

## 2. Buyer pain (Platform Eng)
- Bank policy forbids SaaS for LLM traffic. SecOps blocks egress to vendor SaaS.
- Need k8s-native install with our existing Helm/ArgoCD stack, not a bespoke installer.
- Must ship logs to corporate Splunk/Sentinel and run behind internal CA.

## 3. Sub-features
- [must-have] Production `docker-compose.prod.yml` (api + web + Postgres + Redis + reverse proxy). Today: dev-only compose. (table-stakes prod artifact)
- [must-have] Helm chart `deploy/helm/ai-portal/` (Deployment, Service, Ingress, HPA, ConfigMap, Secret, ServiceAccount). (k8s shops won't accept compose)
- [must-have] One-command install: `./scripts/install.sh` (preflight, env, migrate, smoke test). (under-1-day install bar)
- [must-have] External Postgres + Redis support (no in-cluster DB by default). `deployment_mode=selfhosted` gated in `core/config.py`. (banks own their data tier)
- [must-have] Structured JSON logs to stdout, Splunk HEC + Sentinel sinks via env. (SIEM ingestion is mandatory)
- [must-have] Security doc + data-flow diagram (`docs/security/data-flow.md`). (SecOps gate)
- [must-have] Air-gapped install: pinned digests, offline tarball script. (egress-blocked VPCs need it)
- [must-have] Runbook + RPO/RTO doc. (operational acceptance bar; bank platform team demands before go-live)
- [nice-to-have] Postgres HA recipe (Patroni or CNPG) — doc only. (avoid operator scope creep)
- [nice-to-have] TLS termination via cert-manager. (most banks already have ingress TLS)
- [nice-to-have] OpenShift / Rancher chart variants — design-partner-triggered. (FR banks run OCP; vanilla k8s misses half the market)
- [nice-to-have] FIPS 140-2 / 140-3 image variant. (regulated workloads demand it)
- [skip until design-partner asks] SBOM (CycloneDX via syft). (procurement nice-to-have, not blocker)
- [skip until design-partner asks] Cosign signing + SLSA provenance. (same)
- [skip] Operator/CRD. (Helm is enough)

## 4. Actionable tasks
1. Add `docker-compose.prod.yml` at repo root. Nginx, healthchecks, resource limits.
2. Create `deploy/helm/ai-portal/`. Reuse api + frontend Dockerfiles.
3. Add `scripts/install.sh` — checks tools, prompts secrets, alembic, `/health`.
4. Wire log shipper in `core/logging.py` — JSON, HEC sink behind env.
5. Pin digests: `deploy/images.lock`. Add `scripts/offline-bundle.sh`.
6. Write `docs/security/data-flow.md` — mermaid, trust boundaries, egress matrix.
7. Write `docs/ops/runbook.md` + RPO/RTO targets.
8. E2E: `selfhosted-setup.spec.ts` — first-boot wizard.

## 5. Competitive note
Portkey self-hosted is Docker-only, no Helm. LiteLLM ships chart, no air-gap. Cloudflare AI Gateway has no self-host. Parity = Helm + air-gap; differentiate on EU residency proof.

## 6. Risks
- Helm vs compose drift; SoT = env contract in `core/config.py`.
- Postgres HA scope creep; ship CNPG values, not our operator.
- SIEM auth varies; Splunk HEC first, Sentinel via Fluent Bit second.
- Bank network policies block egress (telemetry, image pulls); install fails silently. Mitigate: preflight egress probe + offline bundle default.
- Air-gapped pressure returns post-scope-cut; keep offline tarball path warm even if deprioritised.
- Postgres version mismatch (bank standard vs our schema) = migration headache; pin supported PG range, test matrix in CI.

## 7. Done-when
Platform Eng installs via `helm install` against external Postgres in under 30 min, sees logs in Splunk, passes smoke test.
