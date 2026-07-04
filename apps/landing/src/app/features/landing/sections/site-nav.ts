import { ChangeDetectionStrategy, Component } from '@angular/core';
import { Prism } from '../../../shared/prism/prism';
import { ThemeToggle } from './theme-toggle';
import { APP_URL } from '../landing.tokens';

@Component({
  selector: 'vx-site-nav',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Prism, ThemeToggle],
  template: `
    <!-- announce bar -->
    <div class="announce">
      <div class="announce-inner">
        <b>Vortex is open for enterprise beta</b> — one endpoint, every provider, full
        governance. <span style="color:var(--vx-violet);">→</span>
      </div>
    </div>

    <!-- nav (maps to kouji-ui: BrandLockup + Button) -->
    <nav class="nav">
      <div class="wrap nav-inner">
        <a href="#top" style="display:flex; align-items:center; gap:11px;">
          <vx-prism [size]="26" [rays]="true" gradId="pmNav" />
          <span class="wordmark">Vortex</span>
        </a>
        <div class="nav-links">
          <a href="#product">Product</a>
          <a href="#providers">Providers</a>
          <a href="#governance">Governance</a>
          <a href="#pricing">Pricing</a>
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
