import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RevealDirective } from '../../../shared/reveal/reveal.directive';

@Component({
  selector: 'vx-governance',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RevealDirective],
  template: `
    <section id="governance" class="wrap section-pad" style="padding-top:0;">
      <div class="section-head" vxReveal>
        <div class="eyebrow"><span class="tick"></span>THE MOAT</div>
        <h2 class="h-display">Governance, not guesswork.</h2>
        <p class="lede">
          The controls a platform team needs to put an LLM in front of the whole company —
          enforced at the gateway, on every request.
        </p>
      </div>

      <div class="gov-grid" vxReveal>
        <div class="gov-card">
          <svg
            class="gov-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.4"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M12 2v20" />
            <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
          </svg>
          <h3>Budgets &amp; hard caps</h3>
          <p>
            Set per-member monthly budgets and hard spend caps. When a cap is hit, requests stop
            — no surprise invoice, no manual chase.
          </p>
          <div class="meta">
            <span>monthly budget</span><span>hard cap</span><span>per member</span>
          </div>
        </div>
        <div class="gov-card">
          <svg
            class="gov-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.4"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <circle cx="9" cy="8" r="3" />
            <path d="M3 20a6 6 0 0 1 12 0" />
            <path d="M16 3.5a3 3 0 0 1 0 5.8" />
            <path d="M17.5 20a6 6 0 0 0-3-5.2" />
          </svg>
          <h3>RBAC + teams &amp; apps</h3>
          <p>
            Roles across org, teams, and apps. Grant model access, scope keys, and delegate
            ownership — without handing everyone a raw provider key.
          </p>
          <div class="meta">
            <span>org</span><span>teams</span><span>apps</span><span>keys</span>
          </div>
        </div>
        <div class="gov-card">
          <svg
            class="gov-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.4"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <rect x="4" y="3" width="16" height="18" rx="2" />
            <path d="M8 8h8" />
            <path d="M8 12h8" />
            <path d="M8 16h5" />
          </svg>
          <h3>Hash-chained audit</h3>
          <p>
            Every request is logged into a tamper-evident, hash-chained trail. Prove what ran,
            when, by whom — with a chain that can't be quietly edited.
          </p>
          <div class="meta">
            <span>tamper-evident</span><span>immutable</span><span>exportable</span>
          </div>
        </div>
        <div class="gov-card">
          <svg
            class="gov-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.4"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M3 3v18h18" />
            <path d="M7 15l3.5-4 3 2.5L21 7" />
          </svg>
          <h3>Cost attribution</h3>
          <p>
            Break every dollar down by team, member, app, key, and model. Real chargeback and
            forecasting, not a single opaque provider bill.
          </p>
          <div class="meta">
            <span>team</span><span>member</span><span>app</span><span>model</span>
          </div>
        </div>
      </div>
    </section>
  `,
})
export class Governance {}
