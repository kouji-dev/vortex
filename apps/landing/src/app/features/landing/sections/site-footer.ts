import { ChangeDetectionStrategy, Component } from '@angular/core';
import { Prism } from '../../../shared/prism/prism';

@Component({
  selector: 'vx-site-footer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Prism],
  template: `
    <footer>
      <div class="wrap">
        <div class="foot-grid">
          <div class="foot-brand">
            <a href="#top" style="display:flex; align-items:center; gap:10px;">
              <vx-prism [size]="24" [rays]="false" gradId="pmFoot" />
              <span class="wordmark" style="font-size:17px;">Vortex</span>
            </a>
            <p>
              The enterprise LLM gateway. One endpoint, every provider, full governance — SaaS or
              self-hosted.
            </p>
          </div>
          <div class="foot-col">
            <h4>Product</h4>
            <a href="#product">Drop-in</a>
            <a href="#governance">Governance</a>
            <a href="#pricing">Pricing</a>
            <a href="#">Changelog</a>
          </div>
          <div class="foot-col">
            <h4>Providers</h4>
            <a href="#providers">OpenAI · Anthropic</a>
            <a href="#providers">Google · Vertex</a>
            <a href="#providers">Azure · Bedrock</a>
            <a href="#providers">Bring your own keys</a>
          </div>
          <div class="foot-col">
            <h4>Docs</h4>
            <a href="#">Quickstart</a>
            <a href="#">SDK compatibility</a>
            <a href="#">Self-hosting</a>
            <a href="#">API reference</a>
          </div>
          <div class="foot-col">
            <h4>Company</h4>
            <a href="#">About</a>
            <a href="#">Security</a>
            <a href="#">Privacy</a>
            <a href="#">Terms</a>
          </div>
        </div>
        <div class="foot-bottom">
          <span>© 2026 Vortex — Enterprise LLM Gateway</span>
          <span>gateway.vortex.ai</span>
        </div>
      </div>
    </footer>
  `,
})
export class SiteFooter {}
