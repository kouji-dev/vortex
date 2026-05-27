# Audit Log

## 1. Purpose
Tamper-evident record of every gateway call, policy decision, key event. Source of truth for compliance.

## 2. Buyer pain (CISO/RSSI)
- EU AI Act Art. 12: high-risk = auto-log over lifecycle.
- GDPR Art. 30: prove who saw what PII, when, via which model.
- DORA + bank audit: 5-7yr immutable LLM trail. ChatGPT Enterprise = CSV, not regulator-grade.

## 3. Sub-features
- Call row: ts, org, user, key_id, model, route, latency, tokens, cost, status [must] (evidence)
- Prompt/response: redacted + SHA-256 [must] (GDPR+forensics)
- Per-org retention toggle, default OFF [must] (GDPR-safe)
- Policy: rule_id, verdict, matches [must] (enforcement proof)
- Key lifecycle [must] (DORA)
- Actor chain user->key->route->provider [must] (Art.30)
- SYNC hash-chain, prev+row_hash same tx [must] (async=rewrite window)
- DB append-only PG trigger [must] (DB-level guarantee)
- Admin filter + JSONL/CSV export [must] (self-serve)
- S3/GCS WORM 7yr [nice] (cold)
- S3 Object Lock / Azure Immutable Blob [nice] (bank ask)
- SIEM webhook [nice] (SOC)
- Sigstore bundles [skip]
- Blockchain [skip] (theatre)

## 4. Tasks
1. `audit/model.py` cols: prev_hash, row_hash, prompt/response_sha256, redacted_prompt/response, policy_decisions JSONB, model_id, latency_ms, tokens_in/out, cost_micros.
2. Alembic: cols + BRIN created_at, partial idx event_type, month partitions.
3. event_type: gateway.call, policy.decision, key.{created,rotated,revoked,used}.
4. Orchestrator end-of-turn -> emit gateway.call.
5. `audit/redact.py`: regex (emails, IBAN, CC, FR SSN). Presidio later.
6. SYNC chain in insert tx: row_hash=sha256(prev_hash||canonical_json(row)), SELECT FOR UPDATE last row. No RQ.
7. PG trigger BEFORE UPDATE/DELETE RAISE. Revoke from app role.
8. Org `audit_full_capture` gates body.
9. `audit/router.py` filters + export.
10. `AuditDetailDrawer.tsx`: chips + redacted diff.
11. E2E `audit-gateway-call.spec.ts`: chat -> assert row + chain.

## 5. Competitive
Portkey: all-or-nothing body. LiteLLM: no chain, weak redact. Cloudflare AI Gateway: analytics, not compliance. Wedge = EU WORM + per-org redaction + DB append-only.

## 6. Risks
- Full prompts = GDPR liability. Default OFF; opt-in + DPA.
- Sync chain adds per-call latency (lock+hash). Mitigate: tiny payload, single-row lock, p95<5ms. Cost of tamper-evidence.
- Row-lock contention high QPS. Mitigate: per-org shards.
- EU AI Act retention may shift (6mo vs 7yr). Per-org TTL.
- Bank may demand S3 Object Lock / Azure Immutable Blob. Design sink contract now.
- Volume: 1M/day ~3GB/mo. Month partitions day one.
- Redaction false negatives: regex now, Presidio Phase 2.

## 7. Done-when
Chat -> audit row w/ hashes, redacted body, verdict, key_id. Export JSONL. Verify chain one-liner. Auditor cannot mutate.
