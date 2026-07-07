import { Injectable } from '@angular/core';

/** Cost-explorer slicing dimension. */
export type CostDim = 'team' | 'member' | 'app' | 'key' | 'model';
/** Spend-chart window. */
export type DateRange = '7d' | '30d' | 'mtd';

export interface DimOption {
  id: CostDim;
  label: string;
}

/** One column in the spend chart. */
export interface SpendPoint {
  /** Axis tick (blank = unlabelled minor tick). */
  label: string;
  value: number;
}

/** A row in the cost-breakdown table for the active dimension. */
export interface BreakdownRow {
  label: string;
  /** Optional provider/team qualifier shown under the label. */
  sub?: string;
  requests: number;
  tokens: number;
  cost: number;
  /** Month-over-month delta, e.g. +12.4. */
  trend: number;
  /** Technical (service) actor — rendered with a cpu glyph. */
  technical?: boolean;
  /** Flagged spend spike. */
  spike?: boolean;
}

export interface TeamBudget {
  name: string;
  /** Default budget per member / month. */
  def: number;
  enforce: 'hard' | 'soft';
  members: number;
  /** Count of member-specific override rules. */
  overrides: number;
  spent: number;
}

export interface MemberBudget {
  name: string;
  team: string;
  source: 'override' | 'default';
  ceiling: number;
  spent: number;
  technical?: boolean;
  enforce: 'hard' | 'soft';
}

export type LogStatus = 'ok' | 'error' | 'blocked' | 'throttled';

export interface RequestLog {
  time: string;
  member: string;
  app: string;
  model: string;
  tokensIn: number;
  tokensOut: number;
  cost: number;
  status: LogStatus;
  provider: string;
}

/**
 * Usage & Budgets mock data. Mirrors the design mockup's `scrUsage()` /
 * `scrBudgets()` demo figures (Northwind AI org). Wired to the analytics +
 * billing APIs in a later pass; today it renders a realistic console.
 */
@Injectable({ providedIn: 'root' })
export class UsageData {
  readonly dimensions: DimOption[] = [
    { id: 'team', label: 'Team' },
    { id: 'member', label: 'Member' },
    { id: 'app', label: 'App' },
    { id: 'key', label: 'API key' },
    { id: 'model', label: 'Model' },
  ];

  readonly ranges: { id: DateRange; label: string }[] = [
    { id: '7d', label: '7d' },
    { id: '30d', label: '30d' },
    { id: 'mtd', label: 'MTD' },
  ];

  /** Daily spend series per window (values in $). */
  private readonly series: Record<DateRange, SpendPoint[]> = {
    '7d': [
      { label: 'Fri', value: 1710 },
      { label: 'Sat', value: 940 },
      { label: 'Sun', value: 880 },
      { label: 'Mon', value: 1980 },
      { label: 'Tue', value: 2140 },
      { label: 'Wed', value: 2260 },
      { label: 'Thu', value: 1284 },
    ],
    '30d': this.buildMonth(30),
    mtd: this.buildMonth(14),
  };

  /** Cost breakdown rows keyed by slicing dimension. */
  private readonly breakdown: Record<CostDim, BreakdownRow[]> = {
    team: [
      { label: 'Platform', requests: 1_313_280, tokens: 930_240_000, cost: 18_240, trend: 12.4 },
      { label: 'Data Science', requests: 707_040, tokens: 500_820_000, cost: 9_820, trend: 8.1 },
      { label: 'Mobile', requests: 442_080, tokens: 313_140_000, cost: 6_140, trend: -3.2 },
      { label: 'Research', requests: 231_120, tokens: 163_710_000, cost: 3_210, trend: 21.0 },
      { label: 'Finance', requests: 72_000, tokens: 51_000_000, cost: 1_000, trend: 2.4 },
    ],
    member: [
      { label: 'svc-chat', sub: 'Platform', requests: 678_240, tokens: 480_420_000, cost: 9_420, trend: 6.8, technical: true },
      { label: 'svc-support', sub: 'Data Science', requests: 449_280, tokens: 318_240_000, cost: 6_240, trend: 4.1, technical: true },
      { label: 'svc-analytics', sub: 'Platform', requests: 295_200, tokens: 209_100_000, cost: 4_100, trend: -1.5, technical: true },
      { label: 'Priya Raman', sub: 'Data Science', requests: 173_520, tokens: 122_910_000, cost: 2_410, trend: 9.0 },
      { label: 'Marcus Reed', sub: 'Platform', requests: 171_360, tokens: 121_380_000, cost: 2_380, trend: 44.2, spike: true },
      { label: 'Dana Cho', sub: 'Platform', requests: 84_960, tokens: 60_180_000, cost: 1_180, trend: 3.3 },
      { label: 'Wei Zhang', sub: 'Research', requests: 70_560, tokens: 49_980_000, cost: 980, trend: 11.7 },
      { label: 'Leo Martins', sub: 'Mobile', requests: 46_080, tokens: 32_640_000, cost: 640, trend: -6.0 },
      { label: 'Sara Okafor', sub: 'Finance', requests: 8_640, tokens: 6_120_000, cost: 120, trend: 1.0 },
    ],
    app: [
      { label: 'Chat', sub: 'system', requests: 678_240, tokens: 480_420_000, cost: 9_420, trend: 6.8 },
      { label: 'Support Copilot', sub: 'service', requests: 449_280, tokens: 318_240_000, cost: 6_240, trend: 4.1 },
      { label: 'Analytics ETL', sub: 'service', requests: 295_200, tokens: 209_100_000, cost: 4_100, trend: -1.5 },
      { label: 'Research Notebook', sub: 'personal', requests: 15_120, tokens: 10_710_000, cost: 210, trend: 18.0 },
      { label: "Leo’s Playground", sub: 'personal', requests: 12_960, tokens: 9_180_000, cost: 180, trend: 5.5 },
    ],
    key: [
      { label: 'svc-chat · default', requests: 678_240, tokens: 480_420_000, cost: 9_420, trend: 6.8, technical: true },
      { label: 'svc-support · default', requests: 449_280, tokens: 318_240_000, cost: 6_240, trend: 4.1, technical: true },
      { label: 'svc-analytics · legacy', requests: 295_200, tokens: 209_100_000, cost: 4_100, trend: -1.5, technical: true },
      { label: 'Priya · default', requests: 173_520, tokens: 122_910_000, cost: 2_410, trend: 9.0 },
      { label: 'Marcus · default', requests: 171_360, tokens: 121_380_000, cost: 2_380, trend: 58.0, spike: true },
      { label: 'Dana · ci-pipeline', requests: 59_040, tokens: 41_820_000, cost: 820, trend: -4.0 },
    ],
    model: [
      { label: 'claude-sonnet-4.5', sub: 'Anthropic', requests: 965_600, tokens: 684_040_000, cost: 4_760, trend: 10.1 },
      { label: 'gpt-4o', sub: 'OpenAI', requests: 653_200, tokens: 462_780_000, cost: 3_220, trend: 5.4 },
      { label: 'gemini-2.5-pro', sub: 'Google', requests: 426_000, tokens: 301_770_000, cost: 2_100, trend: 14.9 },
      { label: 'claude-haiku-4', sub: 'Anthropic', requests: 340_800, tokens: 241_416_000, cost: 1_680, trend: -2.2 },
      { label: 'gpt-4o-mini', sub: 'OpenAI', requests: 255_600, tokens: 181_062_000, cost: 1_260, trend: 7.7 },
    ],
  };

  readonly orgBudget = { spent: 38_410, ceiling: 54_500 };

  readonly teamBudgets: TeamBudget[] = [
    { name: 'Platform', def: 1_500, enforce: 'hard', members: 14, overrides: 3, spent: 18_240 },
    { name: 'Data Science', def: 2_000, enforce: 'soft', members: 9, overrides: 1, spent: 9_820 },
    { name: 'Mobile', def: 800, enforce: 'hard', members: 6, overrides: 0, spent: 6_140 },
    { name: 'Research', def: 1_200, enforce: 'soft', members: 5, overrides: 0, spent: 3_210 },
    { name: 'Finance', def: 400, enforce: 'soft', members: 3, overrides: 0, spent: 1_000 },
  ];

  readonly memberBudgets: MemberBudget[] = [
    { name: 'Dana Cho', team: 'Platform', source: 'default', ceiling: 1_500, spent: 1_180, enforce: 'hard' },
    { name: 'Marcus Reed', team: 'Platform', source: 'override', ceiling: 2_500, spent: 2_380, enforce: 'hard' },
    { name: 'Priya Raman', team: 'Data Science', source: 'override', ceiling: 3_000, spent: 2_410, enforce: 'soft' },
    { name: 'Leo Martins', team: 'Mobile', source: 'default', ceiling: 800, spent: 640, enforce: 'hard' },
    { name: 'Wei Zhang', team: 'Research', source: 'default', ceiling: 1_200, spent: 980, enforce: 'soft' },
    { name: 'Sara Okafor', team: 'Finance', source: 'default', ceiling: 400, spent: 120, enforce: 'soft' },
    { name: 'svc-chat', team: 'Platform', source: 'override', ceiling: 12_000, spent: 9_420, technical: true, enforce: 'hard' },
    { name: 'svc-support', team: 'Data Science', source: 'override', ceiling: 8_000, spent: 6_240, technical: true, enforce: 'soft' },
    { name: 'svc-analytics', team: 'Platform', source: 'override', ceiling: 6_000, spent: 4_100, technical: true, enforce: 'hard' },
  ];

  readonly logs: RequestLog[] = [
    { time: '14:32:07', member: 'svc-chat', app: 'Chat', model: 'claude-sonnet-4.5', provider: 'Anthropic', tokensIn: 1_842, tokensOut: 640, cost: 0.0151, status: 'ok' },
    { time: '14:31:58', member: 'Priya Raman', app: 'Support Copilot', model: 'gpt-4o', provider: 'OpenAI', tokensIn: 3_120, tokensOut: 512, cost: 0.0129, status: 'ok' },
    { time: '14:31:44', member: 'Marcus Reed', app: 'Chat', model: 'claude-sonnet-4.5', provider: 'Anthropic', tokensIn: 12_480, tokensOut: 2_310, cost: 0.0721, status: 'ok' },
    { time: '14:31:39', member: 'svc-support', app: 'Support Copilot', model: 'gpt-4o', provider: 'OpenAI', tokensIn: 2_050, tokensOut: 128, cost: 0.0064, status: 'throttled' },
    { time: '14:31:12', member: 'svc-analytics', app: 'Analytics ETL', model: 'gemini-2.5-pro', provider: 'Google', tokensIn: 8_900, tokensOut: 1_020, cost: 0.0162, status: 'ok' },
    { time: '14:30:55', member: 'Marcus Reed', app: 'Chat', model: 'gpt-4o', provider: 'OpenAI', tokensIn: 980, tokensOut: 0, cost: 0.0, status: 'blocked' },
    { time: '14:30:41', member: 'Leo Martins', app: "Leo’s Playground", model: 'gpt-4o-mini', provider: 'OpenAI', tokensIn: 620, tokensOut: 240, cost: 0.0003, status: 'ok' },
    { time: '14:30:20', member: 'Dana Cho', app: 'Analytics ETL', model: 'gemini-2.5-pro', provider: 'Google', tokensIn: 15_400, tokensOut: 3_200, cost: 0.0353, status: 'ok' },
    { time: '14:29:58', member: 'svc-chat', app: 'Chat', model: 'claude-haiku-4', provider: 'Anthropic', tokensIn: 2_240, tokensOut: 880, cost: 0.0053, status: 'ok' },
    { time: '14:29:33', member: 'Wei Zhang', app: 'Research Notebook', model: 'claude-haiku-4', provider: 'Anthropic', tokensIn: 5_120, tokensOut: 1_640, cost: 0.0107, status: 'ok' },
    { time: '14:29:11', member: 'svc-support', app: 'Support Copilot', model: 'gpt-4o', provider: 'OpenAI', tokensIn: 1_120, tokensOut: 96, cost: 0.0038, status: 'error' },
    { time: '14:28:47', member: 'svc-chat', app: 'Chat', model: 'claude-sonnet-4.5', provider: 'Anthropic', tokensIn: 4_610, tokensOut: 1_180, cost: 0.0315, status: 'ok' },
    { time: '14:28:22', member: 'Sara Okafor', app: 'Chat', model: 'gpt-4o-mini', provider: 'OpenAI', tokensIn: 410, tokensOut: 120, cost: 0.0002, status: 'ok' },
    { time: '14:27:59', member: 'Marcus Reed', app: 'Chat', model: 'claude-sonnet-4.5', provider: 'Anthropic', tokensIn: 22_100, tokensOut: 4_050, cost: 0.1271, status: 'ok' },
    { time: '14:27:30', member: 'svc-analytics', app: 'Analytics ETL', model: 'gemini-2.5-pro', provider: 'Google', tokensIn: 9_800, tokensOut: 0, cost: 0.0, status: 'error' },
  ];

  spendSeries(range: DateRange): SpendPoint[] {
    return this.series[range];
  }

  rows(dim: CostDim): BreakdownRow[] {
    return this.breakdown[dim];
  }

  /** Deterministic month-shaped series (weekday rhythm + upward drift). */
  private buildMonth(days: number): SpendPoint[] {
    const base = [820, 910, 760, 1180, 990, 1290, 620];
    return Array.from({ length: days }, (_, i) => ({
      label: i % 5 === 0 ? `${i + 1}` : '',
      value: Math.round(base[i % 7] * (1 + i * 0.03) + (i % 3) * 60),
    }));
  }
}
