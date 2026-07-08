import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

/** Org roles (plan §Decisions: owner / admin / member). */
export type OrgRole = 'owner' | 'admin' | 'member';

export interface SessionUser {
  id: string;
  email: string;
  name: string;
  role: OrgRole;
  orgId?: string;
  orgName?: string;
}

export interface SignInResult {
  ok: boolean;
  error?: string;
}

/** Shape of GET /api/me — requires auth (401 when signed out); a 200 always
 *  carries a user, but `member` is null for an authed-but-unprovisioned user. */
interface MeResponse {
  user: { id: string; email: string; name?: string | null };
  member: { orgId?: string; role?: OrgRole } | null;
  needsProvision: boolean;
}

/**
 * Session + auth. Components never call HttpClient directly — they go
 * through this service (mirrors preesm's shared/data pattern).
 *
 * Endpoints:
 *   POST /api/auth/sign-in/email  → establish session cookie
 *   GET  /api/me                  → current user (wrapper: {user, member, …})
 *   POST /api/auth/sign-out       → clear session
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);

  /** Current user, or null when signed out. `undefined` = not yet loaded. */
  readonly user = signal<SessionUser | null | undefined>(undefined);

  isAdmin(): boolean {
    const role = this.user()?.role;
    return role === 'owner' || role === 'admin';
  }

  async loadSession(): Promise<SessionUser | null> {
    try {
      // /api/me requires auth: 401 when signed out → rejected → caught below,
      // clearing the user. A resolved response always carries `.user`.
      const res = await firstValueFrom(this.http.get<MeResponse>('/api/me'));
      if (!res?.user) {
        this.user.set(null);
        return null;
      }
      const user: SessionUser = {
        id: res.user.id,
        email: res.user.email,
        name: res.user.name ?? res.user.email,
        role: res.member?.role ?? 'member',
        orgId: res.member?.orgId,
      };
      this.user.set(user);
      return user;
    } catch {
      this.user.set(null);
      return null;
    }
  }

  async signIn(
    email: string,
    password: string,
    rememberMe = false,
  ): Promise<SignInResult> {
    try {
      await firstValueFrom(
        this.http.post('/api/auth/sign-in/email', { email, password, rememberMe }),
      );
    } catch (err) {
      return { ok: false, error: this.errorMessage(err) };
    }
    const user = await this.loadSession();
    if (!user) return { ok: false, error: 'Could not load session' };
    return { ok: true };
  }

  /** Create an account (email + password), then load the new session
   *  (autoSignIn is enabled server-side). */
  async signUp(name: string, email: string, password: string): Promise<SignInResult> {
    try {
      await firstValueFrom(
        this.http.post('/api/auth/sign-up/email', { name, email, password }),
      );
    } catch (err) {
      return { ok: false, error: this.errorMessage(err) };
    }
    const user = await this.loadSession();
    if (!user) return { ok: false, error: 'Could not load session' };
    return { ok: true };
  }

  /** Request a password-reset link. Always resolves calmly (the caller shows a
   *  neutral confirmation regardless, to avoid leaking which emails exist). */
  async requestPasswordReset(email: string): Promise<SignInResult> {
    try {
      await firstValueFrom(
        this.http.post('/api/auth/request-password-reset', {
          email,
          redirectTo: window.location.origin + '/reset-password',
        }),
      );
      return { ok: true };
    } catch (err) {
      return { ok: false, error: this.errorMessage(err) };
    }
  }

  /** Complete a password reset using the token from the emailed link. */
  async resetPassword(newPassword: string, token: string): Promise<SignInResult> {
    try {
      await firstValueFrom(
        this.http.post('/api/auth/reset-password', { newPassword, token }),
      );
      return { ok: true };
    } catch (err) {
      return { ok: false, error: this.errorMessage(err) };
    }
  }

  /** Start an OAuth sign-in (GitHub / Google) — redirects to the provider. */
  async signInWithProvider(provider: 'github' | 'google'): Promise<void> {
    const res = await firstValueFrom(
      this.http.post<{ url?: string; redirect?: boolean }>(
        '/api/auth/sign-in/social',
        { provider, callbackURL: window.location.origin + '/' },
      ),
    );
    if (res?.url) window.location.href = res.url;
  }

  async signOut(): Promise<void> {
    try {
      await firstValueFrom(this.http.post('/api/auth/sign-out', {}));
    } catch {
      /* best-effort — clear locally regardless */
    }
    this.user.set(null);
  }

  private errorMessage(err: unknown): string {
    const e = err as { status?: number; error?: { message?: string } };
    if (e?.error?.message) return e.error.message;
    if (e?.status === 401) return 'Invalid email or password';
    if (e?.status === 0) return 'Cannot reach the server';
    return 'Sign-in failed';
  }
}
