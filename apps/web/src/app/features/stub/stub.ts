import { Component, inject } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { KjIconDirective } from '@kouji-ui/core';

/** Placeholder screen — renders the route's title/sub from route `data`.
 *  Each nav destination resolves here until its feature is built out. */
@Component({
  selector: 'app-stub',
  standalone: true,
  imports: [KjIconDirective],
  styleUrl: './stub.css',
  template: `
    <section class="page">
      <div class="page-head">
        <div>
          <span class="vx-label">{{ title() }}</span>
          <h1>{{ title() }}</h1>
          <p>{{ sub() }}</p>
        </div>
      </div>

      <div class="placeholder" data-testid="stub-placeholder">
        <span class="placeholder-icon" kjIcon="hammer" kjIconSize="lg"></span>
        <div class="placeholder-title">Coming soon</div>
        <div class="placeholder-sub">
          This surface is scaffolded — its screens are being built in a later wave.
        </div>
      </div>
    </section>
  `,
})
export class Stub {
  private readonly route = inject(ActivatedRoute);

  title(): string {
    return (this.route.snapshot.data['title'] as string) ?? 'Screen';
  }
  sub(): string {
    return (this.route.snapshot.data['sub'] as string) ?? '';
  }
}
