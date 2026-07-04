import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import {
  KjButtonComponent,
  KjFieldComponent,
  KjFieldErrorComponent,
  KjFieldLabelComponent,
  KjPasswordInputComponent,
} from '@kouji-ui/components';
import { Prism } from '../../shared/prism/prism';
import { AuthService } from '../../shared/data/auth-service';
import { ThemeToggle } from '../../shared/theme/theme-toggle';

// Completes the forgot-password flow: reads the `token` from the emailed reset
// link (?token=…), sets a new password via better-auth, then routes to sign in.
@Component({
  selector: 'app-reset',
  standalone: true,
  imports: [
    RouterLink,
    KjButtonComponent,
    KjFieldComponent,
    KjFieldLabelComponent,
    KjFieldErrorComponent,
    KjPasswordInputComponent,
    Prism,
    ThemeToggle,
  ],
  styleUrl: './reset.css',
  template: `
    <div class="auth-screen">
      <div class="auth-glow"></div>
      <vx-theme-toggle class="auth-theme-toggle" />
      <div class="auth-body">
        <div class="auth-card">
          <div class="auth-head">
            <div class="brand">
              <vx-prism [size]="40" gradId="vxResetBrand" />
              <span class="brand-word vx-display">Vortex</span>
            </div>
            <h1>Choose a new password</h1>
            <p>Set a new password for your account.</p>
          </div>

          @if (done()) {
            <p class="auth-sent" data-testid="reset-done">
              Your password has been updated — you can sign in now.
            </p>
            <kj-button kjVariant="primary" [kjFullWidth]="true" (click)="goLogin()">
              Go to sign in
            </kj-button>
          } @else if (!token) {
            <p class="auth-sent">This reset link is invalid or has expired.</p>
            <p class="auth-back">
              <a routerLink="/forgot-password">Request a new link</a>
            </p>
          } @else {
            <kj-field [kjInvalid]="!!error()">
              <kj-field-label>New password</kj-field-label>
              <kj-password-input
                data-testid="reset-password"
                kjAutocomplete="new-password"
                kjPlaceholder="At least 12 characters"
                [kjInvalid]="!!error()"
                [(kjValue)]="password"
                (keydown.enter)="onSubmit()"
              />
              @if (error()) {
                <kj-field-error data-testid="reset-error">{{ error() }}</kj-field-error>
              }
            </kj-field>

            <kj-field>
              <kj-field-label>Confirm password</kj-field-label>
              <kj-password-input
                data-testid="reset-confirm"
                kjAutocomplete="new-password"
                kjPlaceholder="Re-enter password"
                [(kjValue)]="confirm"
                (keydown.enter)="onSubmit()"
              />
            </kj-field>

            <kj-button
              kjVariant="primary"
              [kjFullWidth]="true"
              data-testid="reset-submit"
              [kjDisabled]="loading()"
              (click)="onSubmit()"
            >
              {{ loading() ? 'Updating…' : 'Update password' }}
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
export class Reset {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  readonly token = this.route.snapshot.queryParamMap.get('token') ?? '';
  password = '';
  confirm = '';
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly done = signal(false);

  async onSubmit(): Promise<void> {
    if (this.loading()) return;
    this.error.set(null);
    if (this.password.length < 12) {
      this.error.set('Password must be at least 12 characters');
      return;
    }
    if (this.password !== this.confirm) {
      this.error.set('Passwords do not match');
      return;
    }
    this.loading.set(true);
    const result = await this.auth.resetPassword(this.password, this.token);
    this.loading.set(false);
    if (!result.ok) {
      this.error.set(result.error ?? 'Could not reset password');
      return;
    }
    this.done.set(true);
  }

  goLogin(): void {
    void this.router.navigate(['/login']);
  }
}
