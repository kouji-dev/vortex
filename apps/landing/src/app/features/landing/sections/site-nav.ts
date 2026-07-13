import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { Prism } from '../../../shared/prism/prism';
import { ThemeToggle } from './theme-toggle';
import { APP_URL } from '../landing.tokens';

@Component({
  selector: 'vx-site-nav',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Prism, ThemeToggle, RouterLink, RouterLinkActive],
  template: `
    <!-- nav (maps to kouji-ui: BrandLockup + Button) -->
    <nav class="nav">
      <div class="wrap nav-inner">
        <a routerLink="/" style="display:flex; align-items:center; gap:11px;">
          <vx-prism [size]="26" [rays]="true" gradId="pmNav" />
          <span class="wordmark">Vortex</span>
        </a>
        <div class="nav-links">
          <a routerLink="/models" routerLinkActive="active">Models</a>
          <a routerLink="/" fragment="pricing">Pricing</a>
          <a href="#">Docs</a>
        </div>
        <div class="nav-cta">
          <vx-theme-toggle />
          <a class="btn btn-ghost btn-sm" [href]="appUrl">Sign in</a>
          <a class="btn btn-gradient btn-sm" [href]="appUrl">Start free</a>
        </div>
      </div>
    </nav>

    <span id="top"></span>
  `,
})
export class SiteNav {
  readonly appUrl = APP_URL;
}
