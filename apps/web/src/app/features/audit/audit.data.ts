import { Injectable } from '@angular/core';

/** Audit log actor is either a named human/service member or the platform itself. */
export interface AuditEvent {
  /** Sequential event id (newest highest), e.g. 48201. */
  seq: number;
  time: string;
  /** Display name; `system` renders as the platform actor. */
  actor: string;
  system: boolean;
  /** Dotted privileged-action verb, e.g. `key.rotate`, `budget.update`. */
  action: string;
  target: string;
  ip: string;
  /** Short SHA-256 hex of this entry (contents + prev hash). */
  hash: string;
  /** Short SHA-256 hex of the previous entry — the tamper-evident link. */
  prevHash: string;
}

export type AlertSeverity = 'critical' | 'warn' | 'info';
export type AlertStatus = 'open' | 'ack';

export interface Alert {
  id: string;
  severity: AlertSeverity;
  /** Short classifier badge, e.g. `402 Hard cap`, `Spike`, `Idle`. */
  kind: string;
  title: string;
  detail: string;
  /** Affected team or member. */
  entity: string;
  when: string;
  status: AlertStatus;
  tags: string[];
}

/**
 * Audit & Alerts mock data (plan §D6). Mirrors the design mockup's
 * `scrAudit()` / `scrAlerts()` demo figures (Northwind AI org). The audit
 * table conveys a SHA-256 hash chain: each entry's {@link AuditEvent.hash}
 * feeds the next entry's {@link AuditEvent.prevHash}. Wired to the audit +
 * anomaly APIs later; today it renders a realistic, tamper-evident console.
 */
@Injectable({ providedIn: 'root' })
export class AuditData {
  /** Verified-chain banner figures. */
  readonly chain = {
    entries: 48_201,
    verifiedAgo: '2 min ago',
    algo: 'SHA-256 linked',
  };

  /**
   * Newest-first privileged-action ledger. Hashes are precomputed so each
   * row's `prevHash` equals the row below it's `hash` — an unbroken chain.
   */
  readonly events: AuditEvent[] = this.link([
    { actor: 'Dana Cho', system: false, action: 'team.budget.update', target: 'Platform · default $1,500/mo', time: '14:32:08', ip: '10.4.2.19' },
    { actor: 'Priya Raman', system: false, action: 'member.override.set', target: 'Marcus Reed → $2,500/mo', time: '13:58:44', ip: '10.4.2.31' },
    { actor: 'system', system: true, action: 'provider.credential.invalid', target: 'Mistral AI', time: '11:20:02', ip: '—' },
    { actor: 'Leo Martins', system: false, action: 'app.access.grant', target: 'Support Copilot → Mobile team', time: '10:11:37', ip: '10.4.2.44' },
    { actor: 'Dana Cho', system: false, action: 'member.role.change', target: 'Wei Zhang → member', time: '09:47:19', ip: '10.4.2.19' },
    { actor: 'system', system: true, action: 'budget.hardcap.block', target: 'Marcus Reed · 402', time: 'Yesterday 17:03', ip: '—' },
    { actor: 'Priya Raman', system: false, action: 'key.rotate', target: 'svc-support · default', time: 'Yesterday 15:22', ip: '10.4.2.31' },
    { actor: 'system', system: true, action: 'budget.threshold.alert', target: 'Marcus Reed · 95%', time: 'Yesterday 12:00', ip: '—' },
    { actor: 'Dana Cho', system: false, action: 'sso.config.update', target: 'SAML metadata refreshed', time: '2d ago 16:41', ip: '10.4.2.19' },
    { actor: 'system', system: true, action: 'key.idle.flag', target: 'svc-analytics · legacy', time: '2d ago 03:00', ip: '—' },
  ]);

  /** Distinct actors for the filter dropdown. */
  readonly actors: string[] = ['Any', ...unique(this.events.map((e) => e.actor))];
  /** Distinct action namespaces (first segment) for the filter dropdown. */
  readonly actionGroups: string[] = [
    'Any',
    ...unique(this.events.map((e) => e.action.split('.')[0])),
  ];

  readonly alerts: Alert[] = [
    {
      id: 'alt_1', severity: 'critical', kind: '402 Hard cap',
      title: 'Marcus Reed exhausted his budget',
      detail: 'Marcus hit his $2,500/mo override on the Platform team (hard cap). New requests return 402 across all apps until reset.',
      entity: 'Marcus Reed · Platform', when: '12m ago', status: 'open', tags: ['budget', 'member'],
    },
    {
      id: 'alt_2', severity: 'warn', kind: 'Spike',
      title: 'svc-support spend +340% vs baseline',
      detail: 'Service account svc-support (Support Copilot) spent $1,240 in 1h vs a $290 rolling baseline. Possible runaway job.',
      entity: 'svc-support · Data Science', when: '1h ago', status: 'open', tags: ['anomaly', 'app'],
    },
    {
      id: 'alt_3', severity: 'warn', kind: 'Threshold',
      title: 'Marcus Reed crossed 95%',
      detail: 'Marcus reached 95% of his monthly budget. Owners & team admin notified via email + webhook.',
      entity: 'Marcus Reed · Platform', when: 'Yesterday', status: 'ack', tags: ['budget', 'member'],
    },
    {
      id: 'alt_4', severity: 'info', kind: 'Idle',
      title: '1 key unused for 30+ days',
      detail: 'svc-analytics · legacy has had no traffic in 30 days. Consider revoking to reduce attack surface.',
      entity: 'svc-analytics · Platform', when: '2d ago', status: 'open', tags: ['waste', 'key'],
    },
    {
      id: 'alt_5', severity: 'info', kind: 'Under budget',
      title: 'Sara Okafor far under budget',
      detail: 'Sara has used 30% of her $400/mo across the month. Her ceiling may be higher than needed.',
      entity: 'Sara Okafor · Finance', when: '3d ago', status: 'open', tags: ['waste', 'member'],
    },
  ];

  /** Assigns sequential ids + a deterministic hash chain to raw rows. */
  private link(rows: Omit<AuditEvent, 'seq' | 'hash' | 'prevHash'>[]): AuditEvent[] {
    const top = 48_201;
    return rows.map((r, i) => ({
      ...r,
      seq: top - i,
      hash: shortHash(top - i, r.action),
      prevHash: shortHash(top - i - 1, rows[i + 1]?.action ?? 'genesis'),
    }));
  }
}

function unique(xs: string[]): string[] {
  return [...new Set(xs)];
}

/** Deterministic 10-char hex ‘0x…’ digest for a seq/action pair. */
function shortHash(seq: number, action: string): string {
  let h = 0x811c9dc5;
  const src = `${seq}:${action}`;
  for (let i = 0; i < src.length; i++) {
    h ^= src.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  const hex = (h >>> 0).toString(16).padStart(8, '0');
  return `0x${hex}${((seq * 2654435761) >>> 0).toString(16).slice(0, 2)}`;
}
