import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import {
  KjButtonComponent,
  KjCheckboxComponent,
  KjFieldComponent,
  KjFieldErrorComponent,
  KjFieldHelpComponent,
  KjFieldLabelComponent,
  KjInputComponent,
  KjPasswordInputComponent,
} from '@kouji-ui/components';
import { Prism } from '../../shared/prism/prism';
import { AuthService } from '../../shared/data/auth-service';
import { ThemeToggle } from '../../shared/theme/theme-toggle';

@Component({
  selector: 'app-signup',
  standalone: true,
  imports: [
    FormsModule,
    RouterLink,
    KjButtonComponent,
    KjCheckboxComponent,
    KjFieldComponent,
    KjFieldLabelComponent,
    KjFieldHelpComponent,
    KjFieldErrorComponent,
    KjInputComponent,
    KjPasswordInputComponent,
    Prism,
    ThemeToggle,
  ],
  styleUrl: './signup.css',
  template: `
    <div class="auth-screen">
      <div class="auth-glow"></div>
      <vx-theme-toggle class="auth-theme-toggle" />
      <div class="auth-body">
        <div class="auth-card">
          <div class="auth-head">
            <div class="brand">
              <vx-prism [size]="40" gradId="vxSignupBrand" />
              <span class="brand-word vx-display">Vortex</span>
            </div>
            <h1>Create your account</h1>
            <p>Join your organization on Vortex.</p>
          </div>

          <div class="name-grid">
            <kj-field>
              <kj-field-label>First name</kj-field-label>
              <kj-input
                data-testid="signup-first-name"
                autocomplete="given-name"
                placeholder="Dana"
                [(ngModel)]="firstName"
              />
            </kj-field>
            <kj-field>
              <kj-field-label>Last name</kj-field-label>
              <kj-input
                data-testid="signup-last-name"
                autocomplete="family-name"
                placeholder="Cho"
                [(ngModel)]="lastName"
              />
            </kj-field>
          </div>

          <kj-field>
            <kj-field-label>Work email</kj-field-label>
            <kj-input
              type="email"
              data-testid="signup-email"
              autocomplete="username"
              placeholder="you@company.com"
              [(ngModel)]="email"
            />
          </kj-field>

          <kj-field [kjInvalid]="!!error()">
            <kj-field-label>Password</kj-field-label>
            <kj-password-input
              data-testid="signup-password"
              kjAutocomplete="new-password"
              kjPlaceholder="At least 12 characters"
              [kjInvalid]="!!error()"
              [(kjValue)]="password"
            />
            <kj-field-help>12+ characters</kj-field-help>
            @if (error()) {
              <kj-field-error data-testid="signup-error">{{ error() }}</kj-field-error>
            }
          </kj-field>

          <kj-checkbox data-testid="signup-terms" [(checked)]="agreed">
            I agree to the Terms &amp; DPA
          </kj-checkbox>

          <kj-button
            kjVariant="primary"
            [kjFullWidth]="true"
            data-testid="signup-submit"
            [kjDisabled]="loading()"
            (click)="onSubmit()"
          >
            {{ loading() ? 'Creating account…' : 'Create account' }}
          </kj-button>
        </div>

        <p class="auth-alt">
          Already have an account? <a routerLink="/login">Sign in</a>
        </p>
      </div>
    </div>
  `,
})
export class Signup {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  firstName = '';
  lastName = '';
  email = '';
  password = '';
  readonly agreed = signal(false);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  async onSubmit(): Promise<void> {
    if (this.loading()) return;
    this.loading.set(true);
    this.error.set(null);
    const name = `${this.firstName} ${this.lastName}`.trim();
    const result = await this.auth.signUp(name, this.email, this.password);
    this.loading.set(false);

    if (!result.ok) {
      this.error.set(result.error ?? 'Could not create account');
      return;
    }
    await this.router.navigate(['/']);
  }
}
