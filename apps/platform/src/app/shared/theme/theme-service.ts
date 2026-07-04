import { Injectable, PLATFORM_ID, inject, signal } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';

export type VxTheme = 'dark' | 'light';

const STORAGE_KEY = 'vx-theme';

/**
 * Console theme (dark ⇄ light). Mirrors the design's toggle
 * (Vortex.dc.html: `document.documentElement.setAttribute('data-theme', t)`).
 * Persists to localStorage under `vx-theme`; applied on app init.
 * SPA-safe — document/localStorage are guarded for non-browser platforms.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly isBrowser = isPlatformBrowser(inject(PLATFORM_ID));

  /** Active theme. Dark is the canonical brand surface (design default). */
  readonly theme = signal<VxTheme>('dark');

  /** Read the persisted theme and apply it to <html>. Call once on boot. */
  init(): void {
    this.apply(this.stored() ?? 'dark');
  }

  toggle(): void {
    this.apply(this.theme() === 'dark' ? 'light' : 'dark');
  }

  private apply(theme: VxTheme): void {
    this.theme.set(theme);
    if (!this.isBrowser) return;
    try {
      document.documentElement.dataset['theme'] = theme;
    } catch {
      /* non-browser / restricted document */
    }
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* storage unavailable (private mode / quota) */
    }
  }

  private stored(): VxTheme | null {
    if (!this.isBrowser) return null;
    try {
      const v = localStorage.getItem(STORAGE_KEY);
      return v === 'light' || v === 'dark' ? v : null;
    } catch {
      return null;
    }
  }
}
