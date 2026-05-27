# Guardrails

## 1. Purpose
Inline policy on every prompt/response. Block PII, injection, secrets, toxic output before provider/user.

## 2. Buyer pain
- CISO: GDPR Art.32, EU AI Act Art.15 — prove technical controls. Audit on demand.
- DPO: NIR/IBAN/names in OpenAI logs = reportable breach. Needs redaction + evidence.
- Both: shadow-AI risk. No proof = no rollout.

## 3. Sub-features
- EU/FR regex pack MVP: IBAN mod-97, NIR+key, SIREN, email, FR phone, PAN Luhn (FR edge nobody ships) [must-have]
- PII redaction inbound + outbound (regex pack on prompt and reply) [must-have]
- Secrets detection: AWS/GCP/JWT/entropy (credential leak = breach) [must-have]
- Injection heuristics: phrase + delimiter (cheap floor) [must-have]
- Per-workspace YAML policy: allow/redact/block (buyer tunable) [must-have]
- Block + audit-log decision (DPO evidence) [must-have]
- Pluggable ML detector interface — `Guard` accepts regex + ML backends (regex alone loses RFP to Lakera/Protect AI) [must-have]
- Microsoft Presidio integration (hot-swappable by Phase 2 design partner request) [nice-to-have]
- Code-leak detector (Phase 2 demand) [nice-to-have]
- Toxicity/jailbreak ML via interface — Lakera, Protect AI [nice-to-have]
- Custom regex packs UI (low effort post-MVP) [nice-to-have]
- spaCy fr_core_news NER for FR names (ML latency) [nice-to-have]
- LLM-as-judge injection classifier (too slow/expensive) [skip]
- Output schema validator (orthogonal, app concern) [skip]

## 4. Tasks
1. `guardrails/__init__.py` — `Guard` interface (`scan_input`, `scan_output`).
2. `rules/eu_pii.py` — IBAN mod-97, NIR+key, SIREN, email, FR phone, PAN Luhn.
3. `rules/secrets.py`, `rules/injection.py` — AWS/GCP/JWT/entropy; phrase + delimiter.
4. `engine.py` → `Decision{action, masked_text, hits[]}`.
5. `policy.py` — workspace YAML (`allow|redact|block`).
6. Wire `chat/streaming/orchestrator.py` pre/post-LLM hooks.
7. `audit.py` + `guardrail_events` migration.
8. `api/admin/guardrails.py` + `GuardrailsPage.tsx`.
9. `e2e/guardrails.spec.ts` — IBAN masked; injection blocked.

## 5. Competitive note
Portkey/LiteLLM: generic PII, weak on FR. Lakera: ML-only, costly, US-hosted. We ship EU-regex MVP self-hosted; Presidio/Lakera plug via interface.

## 6. Risks
- Regex coverage gaps = false-negative leak = customer-blocking incident. Mitigate: pluggable ML day 1, audit every decision.
- ML detectors add 50-200ms per call. Mitigate: opt-in per workspace, async outbound scan.
- Injection ML immature → false-positive blocks legit prompts. Mitigate: heuristics default, ML behind flag, allow-list.
- Regex false positives on FR text → workspace allow-list.
- Encoding bypass (base64, homoglyph) — log + flag.
- Buyers demand ML in RFP — counter with pluggable interface + Presidio.

## 7. Done-when
Demo: IBAN + "ignore previous instructions" → blocked, masked, audit row. YAML toggle off → passes through.
