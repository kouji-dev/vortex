import type { ReactNode } from 'react';
import { Link } from '@tanstack/react-router';

export function AuthShell({ children, heroTagline }: { children: ReactNode; heroTagline: string }) {
  return (
    <div className="auth-grid" data-testid="auth-shell">
      <aside className="auth-hero">
        <div className="hero-top">
          <Link to="/" className="brand" aria-label="Home">
            <span className="brand-mark" aria-hidden>VX</span>
            <span className="brand-name">Vortex</span>
          </Link>
        </div>
        <div className="hero-center">
          <div className="auth-rays" aria-hidden />
          <p className="serif text-2xl text-ink leading-tight max-w-[28ch]">{heroTagline}</p>
        </div>
        <div className="hero-bottom mono text-ink-3 text-xs">
          Trusted by enterprise teams · Build {import.meta.env.VITE_BUILD_ID ?? 'dev'}
        </div>
      </aside>
      <section className="auth-form-side">
        <div className="auth-form-card">{children}</div>
      </section>
    </div>
  );
}
