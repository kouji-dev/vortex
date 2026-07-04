import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RevealDirective } from '../../../shared/reveal/reveal.directive';

@Component({
  selector: 'vx-dropin',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RevealDirective],
  template: `
    <section id="product" class="wrap section-pad">
      <div class="section-head" vxReveal>
        <div class="eyebrow"><span class="tick"></span>THE DROP-IN</div>
        <h2 class="h-display">Change one line.</h2>
        <p class="lede">
          Point your base URL at Vortex. Claude Code, Codex, Cursor, and the OpenAI / Anthropic
          SDKs keep working — chat, messages, responses, embeddings. No rewrites, no proxy shims.
        </p>
      </div>

      <div class="code-grid" vxReveal>
        <!-- before -->
        <div class="code-card">
          <div class="code-head">
            <span class="code-label">Before</span>
            <span class="code-tag muted">direct to provider</span>
          </div>
          <div class="code-body">
            <pre><span class="cmt"># .env — one provider, no governance</span>
<span class="k-red">ANTHROPIC_BASE_URL</span>=<span class="k-dim">https://api.anthropic.com</span>
<span class="k-red">ANTHROPIC_API_KEY</span>=<span class="k-dim">sk-ant-•••••</span>

<span class="cmt"># every app carries its own key.</span>
<span class="cmt"># no budgets. no audit. no attribution.</span></pre>
          </div>
        </div>
        <!-- after -->
        <div class="code-card after">
          <div class="code-head">
            <span class="code-label">After</span>
            <span class="code-tag live">through Vortex</span>
          </div>
          <div class="code-body">
            <pre><span class="cmt"># .env — same SDK, one endpoint</span>
<span class="k-grn">ANTHROPIC_BASE_URL</span>=<span class="k-vio">https://gateway.vortex.ai</span>
<span class="k-grn">ANTHROPIC_API_KEY</span>=<span class="k-vio">vtx-live-•••••</span>

<span class="cmt"># budgets, RBAC, and hash-chained</span>
<span class="cmt"># audit apply automatically.</span></pre>
          </div>
        </div>
      </div>

      <div class="works-row" vxReveal>
        <span class="works-pill"><span>✓</span> Claude Code</span>
        <span class="works-pill"><span>✓</span> Codex</span>
        <span class="works-pill"><span>✓</span> Cursor</span>
        <span class="works-pill"><span>✓</span> OpenAI SDK</span>
        <span class="works-pill"><span>✓</span> Anthropic SDK</span>
        <span class="works-pill"><span>✓</span> Embeddings</span>
      </div>
    </section>
  `,
})
export class Dropin {}
