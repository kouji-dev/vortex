import type { ReactNode } from 'react';
import { Link } from '@tanstack/react-router';
import { PrismLogo } from '~/components/brand';

export function AuthShell({ children, heroTagline, heroSub }: {
  children: ReactNode;
  heroTagline: string;
  heroSub?: string;
}) {
  return (
    <div className="auth-grid" data-testid="auth-shell">
      {/* Left: brand/hero panel */}
      <aside className="auth-hero">
        <div className="hero-top">
          <Link to="/" className="auth-brand" aria-label="Home">
            <PrismLogo state="idle" size={22} />
            <span className="auth-brand-name">Vortex</span>
          </Link>
          <span className="auth-brand-env">v2 · eu-west-1</span>
        </div>

        <div className="hero-center">
          {/* Prism stage with orbit rings */}
          <div className="prism-stage">
            <div className="prism-orbit orbit-1" />
            <div className="prism-orbit orbit-2"><span className="orbit-node" /></div>
            <div className="prism-orbit orbit-3"><span className="orbit-node orbit-node-pink" /></div>
            <div className="prism-logo">
              <svg className="prism-trail t-2" viewBox="0 0 80 80" fill="none">
                <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="url(#authPrismGrad)" strokeWidth="2" strokeLinejoin="round"/>
              </svg>
              <svg className="prism-trail t-1" viewBox="0 0 80 80" fill="none">
                <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="url(#authPrismGrad)" strokeWidth="2" strokeLinejoin="round"/>
              </svg>
              <svg className="prism-main" viewBox="0 0 80 80" fill="none">
                <defs>
                  <linearGradient id="authPrismGrad" x1="0" y1="0" x2="80" y2="80">
                    <stop offset="0%" stopColor="#f472b6"/>
                    <stop offset="50%" stopColor="#a78bfa"/>
                    <stop offset="100%" stopColor="#60a5fa"/>
                  </linearGradient>
                  <radialGradient id="authCoreGrad">
                    <stop offset="0%" stopColor="#fff" stopOpacity="1"/>
                    <stop offset="100%" stopColor="#e0d7ff" stopOpacity="0.3"/>
                  </radialGradient>
                </defs>
                <line x1="40" y1="8" x2="68" y2="40" stroke="#f472b6" strokeWidth="1.5" strokeLinecap="round" opacity="0.55"/>
                <line x1="40" y1="8" x2="40" y2="72" stroke="#a78bfa" strokeWidth="1.5" strokeLinecap="round" opacity="0.55"/>
                <line x1="40" y1="8" x2="12" y2="40" stroke="#60a5fa" strokeWidth="1.5" strokeLinecap="round" opacity="0.55"/>
                <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="url(#authPrismGrad)" strokeWidth="2.5" strokeLinejoin="round"/>
                <circle className="prism-core" cx="40" cy="40" r="5" fill="url(#authCoreGrad)"/>
              </svg>
            </div>
          </div>

          <div className="hero-eyebrow">Enterprise AI portal</div>
          <h2 className="hero-title serif">
            {heroTagline.includes('everything') ? (
              <>One portal for every <em>model, tool, and knowledge base</em> your company uses.</>
            ) : heroTagline}
          </h2>
          <p className="hero-sub">
            {heroSub ?? 'Claude · GPT-5 · Gemini · Mistral · local. Governed, observable, and shipped as conversations — not scripts.'}
          </p>
        </div>

        <div className="hero-bottom">
          <div className="hero-cap">
            <span>SOC 2 type II</span>
            <span>EU + US regions</span>
            <span>SSO / SCIM</span>
          </div>
        </div>
      </aside>

      {/* Right: form panel */}
      <section className="auth-form-side">
        <div className="form-topbar">
          <Link to="/" className="form-back">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10 3l-5 5 5 5"/>
            </svg>
            back to Vortex
          </Link>
          <div style={{ flex: 1 }} />
        </div>
        <div className="auth-form-card">{children}</div>
      </section>
    </div>
  );
}
