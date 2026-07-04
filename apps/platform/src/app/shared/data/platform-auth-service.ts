import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

export interface SignInResult {
  ok: boolean;
  error?: string;
}

/**
 * Platform-admin session. Uses the same better-auth backend as the tenant
 * console (POST /api/auth/sign-in/email → session cookie), but access is
 * gated server-side: the `/platform/*` API returns 403 for non platform
 * admins. We probe GET /platform/tenants to confirm platform access.
 *
 * Components never call HttpClient directly — they go through this service.
 */
@Injectable({ providedIn: 'root' })
export class PlatformAuthService {
  private readonly http = inject(HttpClient);

  /** Signed-in platform-admin email, or null. `undefined` = not yet loaded. */
  readonly email = signal<string | null | undefined>(undefined);

  /** Confirm the current cookie belongs to a platform admin. */
  async loadSession(): Promise<string | null> {
    try {
      await firstValueFrom(this.http.get('/platform/tenants'));
      // Session valid + platform admin. Keep any known email; else a label.
      if (this.email() === undefined || this.email() === null) {
        this.email.set('Platform admin');
      }
      return this.email() ?? null;
    } catch {
      this.email.set(null);
      return null;
    }
  }

  async signIn(email: string, password: string): Promise<SignInResult> {
    try {
      await firstValueFrom(
        this.http.post('/api/auth/sign-in/email', { email, password }),
      );
    } catch (err) {
      return { ok: false, error: this.errorMessage(err) };
    }

    // Session established — now confirm platform-admin access.
    try {
      await firstValueFrom(this.http.get('/platform/tenants'));
    } catch (err) {
      const status = (err as { status?: number })?.status;
      if (status === 403) {
        await this.signOut();
        return { ok: false, error: 'This account is not a platform admin.' };
      }
      return { ok: false, error: 'Could not verify platform access.' };
    }

    this.email.set(email);
    return { ok: true };
  }

  /** Start an OAuth sign-in (GitHub / Google) — redirects to the provider. */
  async signInWithProvider(provider: 'github' | 'google'): Promise<void> {
    const res = await firstValueFrom(
      this.http.post<{ url?: string }>('/api/auth/sign-in/social', {
        provider,
        callbackURL: window.location.origin + '/',
      }),
    );
    if (res?.url) window.location.href = res.url;
  }

  async signOut(): Promise<void> {
    try {
      await firstValueFrom(this.http.post('/api/auth/sign-out', {}));
    } catch {
      /* best-effort — clear locally regardless */
    }
    this.email.set(null);
  }

  private errorMessage(err: unknown): string {
    const e = err as { status?: number; error?: { message?: string } };
    if (e?.error?.message) return e.error.message;
    if (e?.status === 401) return 'Invalid email or password';
    if (e?.status === 0) return 'Cannot reach the server';
    return 'Sign-in failed';
  }
}
