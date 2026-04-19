import type { ReactNode } from 'react';

export function AuthFormCard({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div data-testid="auth-form-card">
      <header className="mb-6">
        <h1 className="text-xl font-semibold text-ink leading-tight">{title}</h1>
        {subtitle && <p className="text-ink-3 text-sm mt-1">{subtitle}</p>}
      </header>
      <div className="flex flex-col gap-4">{children}</div>
      {footer && <footer className="mt-6 text-sm text-ink-3">{footer}</footer>}
    </div>
  );
}
