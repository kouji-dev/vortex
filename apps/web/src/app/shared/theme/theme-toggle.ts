import { Component, computed, inject } from '@angular/core';
import { KjIconDirective } from '@kouji-ui/core';
import { ThemeService } from './theme-service';

/**
 * Sun/moon theme toggle. Matches the design's IconButton
 * (Vortex.dc.html: sun when dark, moon when light, 16px).
 * Used on the auth screen and in the console topbar.
 */
@Component({
  selector: 'vx-theme-toggle',
  standalone: true,
  imports: [KjIconDirective],
  template: `
    <button
      type="button"
      class="vx-theme-toggle"
      data-testid="theme-toggle"
      [attr.aria-label]="isDark() ? 'Switch to light theme' : 'Switch to dark theme'"
      [attr.title]="isDark() ? 'Switch to light theme' : 'Switch to dark theme'"
      (click)="theme.toggle()"
    >
      <span [kjIcon]="isDark() ? 'sun' : 'moon'" kjIconSize="sm"></span>
    </button>
  `,
  styles: [
    `
      .vx-theme-toggle {
        display: inline-grid;
        place-items: center;
        width: 32px;
        height: 32px;
        border-radius: var(--vx-radius-sm);
        border: 1px solid var(--vx-line);
        background: transparent;
        color: var(--vx-ink-2);
        cursor: pointer;
        transition:
          background var(--vx-dur-fast) var(--vx-ease),
          color var(--vx-dur-fast) var(--vx-ease),
          border-color var(--vx-dur-fast) var(--vx-ease);
      }
      .vx-theme-toggle:hover {
        background: var(--vx-bg-2);
        color: var(--vx-ink);
        border-color: var(--vx-line-2);
      }
      .vx-theme-toggle:focus-visible {
        outline: 2px solid var(--vx-accent);
        outline-offset: 2px;
      }
    `,
  ],
})
export class ThemeToggle {
  readonly theme = inject(ThemeService);
  readonly isDark = computed(() => this.theme.theme() === 'dark');
}
