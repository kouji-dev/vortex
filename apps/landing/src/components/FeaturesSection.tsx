// landing/src/components/FeaturesSection.tsx — Landing v2 design
import * as React from 'react'

const FEATURES = [
  { num: '01', color: 'var(--pink)',   tag: 'CHAT',         title: 'Streaming from turn one.',       body: 'First byte under a second. Resume, stop, regenerate. Markdown, code, tables rendered. Every message addressable by URL.' },
  { num: '02', color: 'var(--violet)', tag: 'KNOWLEDGE',    title: 'Hybrid retrieval that works.',   body: 'BM25 + pgvector + reranking. Scoped per-conversation. Citations that point to the paragraph, not the file.' },
  { num: '03', color: 'var(--blue)',   tag: 'IDENTITY',     title: 'Sign in the way you want.',      body: 'Google, GitHub, or magic link for teams. Microsoft Entra, OIDC, SAML for enterprise. One identity model, every path.' },
  { num: '04', color: 'var(--pink)',   tag: 'GUARDRAILS',   title: 'Policies that block.',           body: 'PII detection, prompt injection, secrets, custom rules. Per-tenant, per-assistant, audit-logged. Real governance, not security theatre.' },
  { num: '05', color: 'var(--violet)', tag: 'OBSERVABILITY', title: 'Trace every turn.',             body: 'Every run is a tree. See the prompt, the retrieval, the tool calls, the cost. Replay against a new model in one click.' },
  { num: '06', color: 'var(--blue)',   tag: 'SELF-HOST',    title: 'Your infra, your data.',         body: 'Single Docker Compose. Postgres + pgvector + Redis. Deploy to Render, Azure, bare metal. BYO-keys to any provider.' },
]

const DELAYS = [100, 200, 300, 100, 200, 300]

export function FeaturesSection() {
  return (
    <section id="features" style={{ maxWidth: 1280, margin: '0 auto', padding: '120px 32px' }}>
      {/* Header */}
      <div className="section-head reveal">
        <div className="k">Under the hood</div>
        <h2>
          A real product, not a{' '}
          <em className="em">prompt wrapper.</em>
        </h2>
        <p className="sub">
          Conversations persist. Memories compound. KBs index incrementally. Every turn is traced, every token metered. Built by people who've run AI in production — for people about to.
        </p>
      </div>

      {/* Feature grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20 }}>
        {FEATURES.map((f, i) => (
          <div
            key={f.tag}
            className="reveal"
            style={{
              border: '1px solid var(--border)', borderRadius: 12,
              padding: 28, background: 'var(--bg2)',
              transitionDelay: `${DELAYS[i]}ms`,
            }}
          >
            <div style={{
              fontFamily: '"JetBrains Mono", monospace', fontSize: 12,
              color: f.color, marginBottom: 18,
              letterSpacing: '-0.01em',
            }}>
              — {f.num} · {f.tag}
            </div>
            <h3 style={{ margin: '0 0 10px', fontSize: 22, fontWeight: 600, letterSpacing: '-0.02em' }}>{f.title}</h3>
            <p style={{ color: 'var(--text-2)', margin: 0, fontSize: 14, lineHeight: 1.6 }}>{f.body}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
