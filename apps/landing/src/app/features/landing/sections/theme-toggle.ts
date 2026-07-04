import {
  ChangeDetectionStrategy,
  Component,
  PLATFORM_ID,
  afterNextRender,
  inject,
  signal,
} from '@angular/core';
import { isPlatformBrowser } from '@angular/common';

type Theme = 'dark' | 'light';
const STORAGE_KEY = 'vx-theme';

/**
 * Dark/light theme toggle for the landing nav. SSR-safe: renders the default
 * 'dark' (brand stage) on the server; all document/localStorage access is
 * guarded behind afterNextRender / isPlatformBrowser. The choice is persisted
 * in localStorage and re-applied on load. Toggles
 * document.documentElement.dataset.theme between 'dark' and 'light'.
 */
@Component({
  selector: 'vx-theme-toggle',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button
      type="button"
      class="theme-toggle"
      [attr.aria-label]="theme() === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'"
      [attr.aria-pressed]="theme() === 'light'"
      title="Toggle theme"
      (click)="toggle()"
    >
      @if (theme() === 'dark') {
        <!-- sun: click to go light -->
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      } @else {
        <!-- moon: click to go dark -->
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      }
    </button>
  `,
})
export class ThemeToggle {
  private readonly platformId = inject(PLATFORM_ID);
  readonly theme = signal<Theme>('dark');

  constructor() {
    // Browser-only: restore the persisted choice and apply it on load.
    afterNextRender(() => {
      let saved: Theme | null = null;
      try {
        const v = localStorage.getItem(STORAGE_KEY);
        if (v === 'dark' || v === 'light') saved = v;
      } catch {
        /* localStorage may be unavailable (private mode) */
      }
      if (saved) this.apply(saved);
      else this.theme.set(this.currentDomTheme());
    });
  }

  toggle(): void {
    this.apply(this.theme() === 'dark' ? 'light' : 'dark');
  }

  private apply(next: Theme): void {
    this.theme.set(next);
    if (!isPlatformBrowser(this.platformId)) return;
    document.documentElement.dataset['theme'] = next;
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore persistence failures */
    }
  }

  private currentDomTheme(): Theme {
    if (!isPlatformBrowser(this.platformId)) return 'dark';
    return document.documentElement.dataset['theme'] === 'light' ? 'light' : 'dark';
  }
}
