import { Injectable } from '@angular/core';

export interface KpiTile {
  label: string;
  value: string;
  delta: string;
  trend: 'up' | 'down' | 'flat';
}

export interface SpendRow {
  label: string;
  value: string;
  pct: number;
}

/**
 * Overview metrics. Wired to the gateway once the analytics API lands;
 * for now serves the design's mock KPI figures so the console renders
 * a realistic governance dashboard.
 */
@Injectable({ providedIn: 'root' })
export class MetricsService {
  /** Org-wide KPI tiles (spend / requests / tokens + governance). */
  overviewKpis(): KpiTile[] {
    return [
      { label: 'Org spend · MTD', value: '$18,240', delta: '12.4%', trend: 'up' },
      { label: 'Sum of member budgets', value: '$26,500', delta: 'ceiling', trend: 'flat' },
      { label: 'Requests', value: '2.84M', delta: '12.4%', trend: 'up' },
      { label: 'Tokens', value: '1.92B', delta: '9.1%', trend: 'up' },
      { label: 'Active members', value: '38 / 42', delta: '+4', trend: 'up' },
      { label: 'Open alerts', value: '3', delta: '1 critical', trend: 'up' },
    ];
  }

  /** Top spenders by team (mock — the cost explorer will slice this live). */
  topSpenders(): SpendRow[] {
    return [
      { label: 'Platform', value: '$6,120', pct: 100 },
      { label: 'Growth', value: '$4,880', pct: 80 },
      { label: 'Support', value: '$3,410', pct: 56 },
      { label: 'Data Science', value: '$2,240', pct: 37 },
      { label: 'Sandbox', value: '$1,590', pct: 26 },
    ];
  }

  /** Provider request share (mock). */
  providerShare(): SpendRow[] {
    return [
      { label: 'Anthropic', value: '46%', pct: 46 },
      { label: 'OpenAI', value: '32%', pct: 32 },
      { label: 'Google', value: '15%', pct: 15 },
      { label: 'Other', value: '7%', pct: 7 },
    ];
  }
}
