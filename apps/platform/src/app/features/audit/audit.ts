import { Component, inject, signal } from '@angular/core';
import { PlatformService, type AuditEntry } from '../../shared/data/platform-service';

/** Audit — hash-chained platform audit log (plan §D2). */
@Component({
  selector: 'app-audit',
  standalone: true,
  imports: [],
  styleUrls: ['../_shared/console.css'],
  template: `
    <section class="page">
      <div class="page-head">
        <div>
          <span class="vx-label">Super-admin</span>
          <h1>Audit</h1>
          <p>Every super-admin action, hash-chained for tamper evidence.</p>
        </div>
      </div>

      @if (error()) {
        <div class="banner err" data-testid="audit-error">{{ error() }}</div>
      }

      <div class="card">
        <div class="card-head">
          <h2>Audit log</h2>
          <span class="vx-label">{{ entries().length }} entries</span>
        </div>
        @if (loading()) {
          <div class="empty">Loading…</div>
        } @else if (entries().length === 0) {
          <div class="empty" data-testid="audit-empty">No audit entries yet.</div>
        } @else {
          <div class="tbl-wrap">
            <table class="tbl" data-testid="audit-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Admin</th>
                  <th>Action</th>
                  <th>Target org</th>
                  <th>Entry hash</th>
                </tr>
              </thead>
              <tbody>
                @for (e of entries(); track e.id ?? e.entryHash ?? $index) {
                  <tr>
                    <td class="mono">{{ time(e.createdAt) }}</td>
                    <td class="mono">{{ e.adminEmail ?? e.platformAdminId ?? '—' }}</td>
                    <td class="strong">{{ e.action }}</td>
                    <td class="mono">{{ e.targetOrg ?? '—' }}</td>
                    <td class="mono">{{ short(e.entryHash) }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }
      </div>
    </section>
  `,
})
export class Audit {
  private readonly platform = inject(PlatformService);

  readonly entries = signal<AuditEntry[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  constructor() {
    void this.load();
  }

  time(iso: string | null | undefined): string {
    if (!iso) return '—';
    const ts = Date.parse(iso);
    return Number.isNaN(ts) ? iso : new Date(ts).toLocaleString();
  }

  short(hash: string | null | undefined): string {
    return hash ? `${hash.slice(0, 12)}…` : '—';
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    try {
      this.entries.set(await this.platform.audit());
      this.error.set(null);
    } catch {
      this.error.set('Could not load audit log.');
    } finally {
      this.loading.set(false);
    }
  }
}
