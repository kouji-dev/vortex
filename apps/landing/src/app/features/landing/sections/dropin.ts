import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { DomSanitizer, type SafeHtml } from '@angular/platform-browser';
import { RevealDirective } from '../../../shared/reveal/reveal.directive';

/** One language pane of the code showcase: highlighted markup + copyable text. */
interface CodePane {
  id: 'env' | 'curl' | 'ts' | 'py';
  label: string;
  html: SafeHtml;
  text: string;
}

const PANES: { id: CodePane['id']; label: string; html: string }[] = [
  {
    id: 'env',
    label: '.env',
    html: `<span class="cmt"># .env — same SDK, one endpoint. change one line:</span>
<span class="strike">ANTHROPIC_BASE_URL=https://api.anthropic.com</span>
<span class="hl-line"><span class="k-grn">ANTHROPIC_BASE_URL</span>=<span class="k-vio">https://gateway.vortex.ai</span></span>
<span class="k-grn">ANTHROPIC_API_KEY</span>=<span class="k-vio">vtx-live-•••••</span>

<span class="cmt"># budgets, RBAC, and hash-chained audit</span>
<span class="cmt"># apply automatically. nothing else changes.</span>`,
  },
  {
    id: 'curl',
    label: 'cURL',
    html: `<span class="cmt"># any OpenAI-compatible client works</span>
curl <span class="k-vio">https://gateway.vortex.ai/v1/chat/completions</span> \\
  -H <span class="k-grn">"Authorization: Bearer $VORTEX_API_KEY"</span> \\
  -d <span class="k-grn">'{
    "model": "claude-sonnet-4.5",
    "messages": [{"role":"user","content":"Hello"}]
  }'</span>`,
  },
  {
    id: 'ts',
    label: 'TypeScript',
    html: `<span class="k-vio">import</span> OpenAI <span class="k-vio">from</span> <span class="k-grn">"openai"</span>;

<span class="k-vio">const</span> client = <span class="k-vio">new</span> OpenAI({
<span class="hl-line">  baseURL: <span class="k-grn">"https://gateway.vortex.ai/v1"</span>,</span>
  apiKey: process.env.<span class="k-grn">VORTEX_API_KEY</span>,
});

<span class="k-vio">const</span> res = <span class="k-vio">await</span> client.chat.completions.create({
  model: <span class="k-grn">"gpt-4o"</span>, <span class="cmt">// or any model in the catalog</span>
  messages: [{ role: <span class="k-grn">"user"</span>, content: <span class="k-grn">"Hello"</span> }],
});`,
  },
  {
    id: 'py',
    label: 'Python',
    html: `<span class="k-vio">from</span> openai <span class="k-vio">import</span> OpenAI

client = OpenAI(
<span class="hl-line">    base_url=<span class="k-grn">"https://gateway.vortex.ai/v1"</span>,</span>
    api_key=os.environ[<span class="k-grn">"VORTEX_API_KEY"</span>],
)

res = client.chat.completions.create(
    model=<span class="k-grn">"gemini-2.5-pro"</span>,  <span class="cmt"># route anywhere</span>
    messages=[{<span class="k-grn">"role"</span>: <span class="k-grn">"user"</span>, <span class="k-grn">"content"</span>: <span class="k-grn">"Hello"</span>}],
)`,
  },
];

/** Strip highlight spans back to the plain code for the clipboard. */
function plainText(html: string): string {
  return html.replace(/<[^>]+>/g, '');
}

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

      <div class="code-showcase" vxReveal>
        <span class="vx-orbit" aria-hidden="true"></span>
        <div class="cs-head">
          <span class="cs-dots"><i></i><i></i><i></i></span>
          <div class="cs-tabs">
            @for (p of panes; track p.id) {
              <button class="cs-tab" [class.on]="tab() === p.id" (click)="tab.set(p.id)">
                {{ p.label }}
              </button>
            }
          </div>
          <span class="code-tag live cs-live">through Vortex</span>
          <button class="cs-copy" (click)="copy()">{{ copied() ? 'Copied ✓' : 'Copy' }}</button>
        </div>
        <div class="code-body cs-body">
          @for (p of panes; track p.id) {
            <pre class="cs-pane" [class.on]="tab() === p.id" [innerHTML]="p.html"></pre>
          }
        </div>
      </div>
    </section>
  `,
})
export class Dropin {
  private readonly sanitizer = inject(DomSanitizer);

  /** Highlighted panes — markup is static, authored above (design-exact). */
  readonly panes: CodePane[] = PANES.map((p) => ({
    id: p.id,
    label: p.label,
    html: this.sanitizer.bypassSecurityTrustHtml(p.html),
    text: plainText(p.html),
  }));

  readonly tab = signal<CodePane['id']>('env');
  readonly copied = signal(false);

  copy(): void {
    const pane = this.panes.find((p) => p.id === this.tab());
    if (!pane) return;
    try {
      void navigator.clipboard.writeText(pane.text);
    } catch {
      /* clipboard unavailable (permissions/HTTP) — button feedback still runs */
    }
    this.copied.set(true);
    setTimeout(() => this.copied.set(false), 1400);
  }
}
