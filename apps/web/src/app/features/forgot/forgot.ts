import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  KjButtonComponent,
  KjFieldComponent,
  KjFieldLabelComponent,
  KjInputComponent,
} from '@kouji-ui/components';
import { Prism } from '../../shared/prism/prism';
import { AuthService } from '../../shared/data/auth-service';
import { ThemeToggle } from '../../shared/theme/theme-toggle';

@Component({
  selector: 'app-forgot',
  standalone: true,
  imports: [
    FormsModule,
    RouterLink,
    KjButtonComponent,
    KjFieldComponent,
    KjFieldLabelComponent,
    KjInputComponent,
    Prism,
    ThemeToggle,
  ],
  styleUrl: './forgot.css',
  template: `
    <div class="auth-screen">
      <div class="auth-glow"></div>
      <vx-theme-toggle class="auth-theme-toggle" />
      <div class="auth-body">
        <div class="auth-card">
          <div class="auth-head">
            <div class="brand">
              <vx-prism [size]="40" gradId="vxForgotBrand" />
              <span class="brand-word vx-display">Vortex</span>
            </div>
            <h1>Reset your password</h1>
            <p>Enter your work email and we'll send you a reset link.</p>
          </div>

          @if (sent()) {
            <p class="auth-sent" data-testid="forgot-sent">
              If an account exists for that email, we've sent a reset link.
            </p>
          } @else {
            <kj-field>
              <kj-field-label>Work email</kj-field-label>
              <kj-input
                type="email"
                data-testid="forgot-email"
                autocomplete="username"
                placeholder="you@company.com"
                [(ngModel)]="email"
                (keydown.enter)="onSubmit()"
              />
            </kj-field>

            <kj-button
              kjVariant="primary"
              [kjFullWidth]="true"
              data-testid="forgot-submit"
              [kjDisabled]="loading()"
              (click)="onSubmit()"
            >
              {{ loading() ? 'Sending…' : 'Send reset link' }}
            </kj-button>
          }
        </div>

        <p class="auth-back">
          <a routerLink="/login">← Back to sign in</a>
        </p>
      </div>
    </div>
  `,
})
export class Forgot {
  private readonly auth = inject(AuthService);

  email = '';
  readonly loading = signal(false);
  readonly sent = signal(false);

  async onSubmit(): Promise<void> {
    if (this.loading() || !this.email) return;
    this.loading.set(true);
    await this.auth.requestPasswordReset(this.email);
    this.loading.set(false);
    // Always show the same calm confirmation — never reveal whether the
    // email is registered.
    this.sent.set(true);
  }
}
