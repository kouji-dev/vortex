# Pivot — Enterprise AI Control Plane

**Product:** Self-hosted AI gateway for regulated EU enterprises.
**Wedge:** Govern every prompt, every model, every euro — on your infra.
**We don't build:** general-purpose ChatGPT clones, consumer prosumer UX, model training, fine-tuning infra.

---

## Phase 1 — Gateway (months 0–6)

**Buyer:** CISO / RSSI · Head of Platform Engineering
**Killer demo:** Claude Code in dev's terminal → calls our gateway → audited, redacted, rate-limited, billed, blockable in real time.
**Success metric:** 1 paying design partner in production, 1 active reference call.

### Features
- OpenAI-Compatible API (drop-in for Claude Code, Cursor, Continue, LangChain, custom apps)
- API Key Management
- Multi-Provider Routing (Anthropic, OpenAI, Gemini, Mistral, on-prem) + Failover
- Observability (traces, latency, tokens, errors)
- Audit Log
- Rate Limiting (per-key QPS)
- Cost & Budget Control (hard cutoffs)
- Prompt Caching
- Policies & RBAC
- Guardrails (PII redaction, prompt-injection defense, content filtering, output validation)
- SSO (SAML, Entra)
- CISO Dashboard
- Self-Hosted Deploy (Helm, docker-compose)

### Out of scope (Phase 1)
- Chat UI, knowledge bases, connectors, memories, assistants, agents, workflow templates

---

## Phase 2 — Workspace (months 6–12)

**Buyer:** Head of Productivity · Head of Legal · CFO (expansion inside same account)
**Killer demo:** Legal analyst chats with a contract from Sharepoint, gets a redlined answer, every prompt audited under the same Phase 1 controls.
**Success metric:** 3 paying customers, 50%+ expansion revenue from Phase 1 accounts.

### Features
- Chat (Workspace) with file attachments
- Knowledge Bases
- Connectors (Sharepoint, Confluence, M365, Drive, Slack)
- Policy-Aware Model Picker
- Conversation History & Search
- Shared Conversations (team-scoped)

### Out of scope (Phase 2)
- Autonomous agents, scheduled jobs, vertical workflow templates, memories

---

## Phase 3 — Workflows & Agents (months 12–24)

**Buyer:** Line-of-business owners (Head of Legal, Head of Compliance, Head of Sales Ops)
**Killer demo:** Legal team's contract-review agent runs unattended on a Sharepoint folder, posts redlined drafts to Teams, every step traced and approved.
**Success metric:** 10+ paying customers, 1 named vertical workflow as a reference.

### Features
- Assistants (private, team, org)
- Memories
- Tool Registry / MCP
- Agent Workflows (with human-in-the-loop approval)
- Scheduled / Triggered Agents
- Workflow Templates (legal review, KYC, RFP)
- Agent Evaluation & Tracing

### Out of scope (Phase 3)
- Marketplace, third-party agent publishing, agent-to-agent protocols across orgs
