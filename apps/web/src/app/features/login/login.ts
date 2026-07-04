import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import {
  KjButtonComponent,
  KjCheckboxComponent,
  KjFieldComponent,
  KjFieldErrorComponent,
  KjFieldLabelComponent,
  KjInputComponent,
  KjPasswordInputComponent,
} from '@kouji-ui/components';
import { Prism } from '../../shared/prism/prism';
import { AuthService } from '../../shared/data/auth-service';
import { ThemeToggle } from '../../shared/theme/theme-toggle';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [
    FormsModule,
    RouterLink,
    KjButtonComponent,
    KjCheckboxComponent,
    KjFieldComponent,
    KjFieldLabelComponent,
    KjFieldErrorComponent,
    KjInputComponent,
    KjPasswordInputComponent,
    Prism,
    ThemeToggle,
  ],
  styleUrl: './login.css',
  template: `
    <div class="auth-screen">
      <div class="auth-glow"></div>
      <vx-theme-toggle class="auth-theme-toggle" />
      <div class="auth-body">
      <div class="auth-card">
        <div class="auth-head">
          <div class="brand">
            <vx-prism [size]="40" gradId="vxLoginBrand" />
            <span class="brand-word vx-display">Vortex</span>
          </div>
          <h1>Sign in to Vortex</h1>
          <p>The control plane for your AI spend &amp; access.</p>
        </div>

        <kj-field>
          <kj-field-label>Email address</kj-field-label>
          <kj-input
            type="email"
            data-testid="login-email"
            autocomplete="username"
            placeholder="you@company.com"
            [(ngModel)]="email"
            (keydown.enter)="onSubmit()"
          />
        </kj-field>

        <kj-field [kjInvalid]="!!error()">
          <kj-field-label>Password</kj-field-label>
          <kj-password-input
            data-testid="login-password"
            kjAutocomplete="current-password"
            kjPlaceholder="••••••••"
            [kjInvalid]="!!error()"
            [(kjValue)]="password"
            (keydown.enter)="onSubmit()"
          />
          @if (error()) {
            <kj-field-error data-testid="login-error">{{ error() }}</kj-field-error>
          }
        </kj-field>

        <div class="auth-row">
          <kj-checkbox data-testid="login-remember" [(checked)]="rememberMe">
            Remember me
          </kj-checkbox>
          <a class="auth-forgot vx-mono" routerLink="/forgot-password">Forgot?</a>
        </div>

        <kj-button
          kjVariant="primary"
          [kjFullWidth]="true"
          data-testid="login-submit"
          [kjDisabled]="loading()"
          (click)="onSubmit()"
        >
          {{ loading() ? 'Signing in…' : 'Sign in' }}
        </kj-button>

        <div class="auth-divider"><span>or continue with</span></div>

        <div class="auth-social">
          <kj-button
            kjVariant="secondary"
            [kjFullWidth]="true"
            data-testid="login-github"
            (click)="social('github')"
          >
            <svg class="social-ic" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path
                d="M12 .5C5.37.5 0 5.87 0 12.5c0 5.3 3.44 9.8 8.21 11.39.6.11.82-.26.82-.58 0-.29-.01-1.04-.02-2.05-3.34.73-4.04-1.61-4.04-1.61-.55-1.39-1.34-1.76-1.34-1.76-1.09-.75.08-.73.08-.73 1.2.08 1.84 1.24 1.84 1.24 1.07 1.83 2.81 1.3 3.5.99.11-.78.42-1.3.76-1.6-2.67-.3-5.47-1.33-5.47-5.93 0-1.31.47-2.38 1.24-3.22-.13-.3-.54-1.52.11-3.18 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 0 1 6 0c2.29-1.55 3.3-1.23 3.3-1.23.65 1.66.24 2.88.12 3.18.77.84 1.23 1.91 1.23 3.22 0 4.61-2.81 5.63-5.49 5.92.43.37.81 1.1.81 2.22 0 1.61-.01 2.9-.01 3.29 0 .32.21.7.82.58A12 12 0 0 0 24 12.5C24 5.87 18.63.5 12 .5Z"
              />
            </svg>
            GitHub
          </kj-button>
          <kj-button
            kjVariant="secondary"
            [kjFullWidth]="true"
            data-testid="login-google"
            (click)="social('google')"
          >
            <svg class="social-ic" viewBox="0 0 24 24" aria-hidden="true">
              <path
                fill="#4285f4"
                d="M23.52 12.27c0-.82-.07-1.6-.2-2.36H12v4.46h6.47a5.53 5.53 0 0 1-2.4 3.63v3.02h3.88c2.27-2.09 3.57-5.17 3.57-8.75Z"
              />
              <path
                fill="#34a853"
                d="M12 24c3.24 0 5.96-1.08 7.95-2.91l-3.88-3.02c-1.08.72-2.45 1.15-4.07 1.15-3.13 0-5.78-2.11-6.73-4.96H1.28v3.12A12 12 0 0 0 12 24Z"
              />
              <path
                fill="#fbbc05"
                d="M5.27 14.26a7.2 7.2 0 0 1 0-4.52V6.62H1.28a12 12 0 0 0 0 10.76l3.99-3.12Z"
              />
              <path
                fill="#ea4335"
                d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.44-3.44A11.98 11.98 0 0 0 12 0 12 12 0 0 0 1.28 6.62l3.99 3.12C6.22 6.86 8.87 4.75 12 4.75Z"
              />
            </svg>
            Google
          </kj-button>
        </div>
      </div>

      <p class="auth-alt">
        New here? <a routerLink="/signup">Create an account</a>
      </p>
      </div>
    </div>
  `,
})
export class Login {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  email = '';
  password = '';
  readonly rememberMe = signal(false);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  async onSubmit(): Promise<void> {
    if (this.loading()) return;
    this.loading.set(true);
    this.error.set(null);
    const result = await this.auth.signIn(this.email, this.password, this.rememberMe());
    this.loading.set(false);

    if (!result.ok) {
      this.error.set(result.error ?? 'Invalid credentials');
      return;
    }
    await this.router.navigate(['/']);
  }

  async social(provider: 'github' | 'google'): Promise<void> {
    this.error.set(null);
    try {
      await this.auth.signInWithProvider(provider);
    } catch {
      this.error.set('Could not start ' + provider + ' sign-in');
    }
  }
}
