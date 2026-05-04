import type { ReactNode } from 'react';

export function AuthFormCard({
  title,
  eyebrow,
  subtitle,
  children,
  footer,
}: {
  title: string;
  eyebrow?: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div data-testid="auth-form-card">
      <header className="mb-6">
        {eyebrow && <div className="form-eyebrow">{eyebrow}</div>}
        <h1 className="form-title serif">{title}</h1>
        {subtitle && <p className="form-desc">{subtitle}</p>}
      </header>
      <div>{children}</div>
      {footer && <footer className="form-foot">{footer}</footer>}
    </div>
  );
}
