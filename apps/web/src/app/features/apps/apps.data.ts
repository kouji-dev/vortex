import { Injectable } from '@angular/core';

/** Provider identity keys used by routing marks. */
export type RouteProvider = 'anthropic' | 'openai' | 'google';

export interface RouteProviderMeta {
  color: string;
  letter: string;
  label: string;
}

/** Kind of thing that calls the gateway. */
export type AppKind = 'system' | 'service' | 'personal';
export type AppStatus = 'active' | 'paused';

/** Principal a grant is issued to. */
export type PrincipalType = 'team' | 'member';
export type AppRole = 'app_admin' | 'app_member';

/** An access grant — a team or member allowed to use / admin an app. */
export interface AppGrant {
  who: string;
  principalType: PrincipalType;
  role: AppRole;
  /** How the grant was issued — team grant / direct / inherited. */
  via: string;
}

/** A service key (vtx_…) owned by the app's technical member. */
export interface ServiceKey {
  name: string;
  kind: 'default' | 'personal';
  mask: string;
  status: 'active' | 'stale';
  rules: string;
  rate: string;
  created: string;
  lastUsed: string;
}

/** One hop in the app's failover routing chain. */
export interface RouteHop {
  model: string;
  prov: RouteProvider;
  role: string;
  binding: string;
}

/** A labelled spend row for the usage breakdowns. */
export interface UsageRow {
  label: string;
  value: number;
  prov?: RouteProvider;
}

/** A deployable app / service that calls the gateway. */
export interface App {
  id: string;
  name: string;
  kind: AppKind;
  owner: string;
  /** Technical member (service account) chip, or '—' for personal apps. */
  tech: string;
  /** Human summary of who has access. */
  access: string;
  status: AppStatus;
  /** Month-to-date spend, USD. */
  spend: number;
  /** MTD request volume. */
  requests: number;
  /** p50 latency, ms. */
  latency: number;
  /** Error rate, %. */
  errRate: number;
  /** Primary model / route policy. */
  policy: string;
  grants: AppGrant[];
  keys: ServiceKey[];
  routing: RouteHop[];
  usageByMember: UsageRow[];
  usageByModel: UsageRow[];
}

/** An app the current member can access — with their role, what they can do
 *  and their own usage against it (member "My Apps" screen). */
export interface MemberApp {
  id: string;
  name: string;
  kind: AppKind;
  policy: string;
  /** The current member's role on this app. */
  role: AppRole;
  /** Plain-language summary of what the member can do here. */
  can: string;
  /** The member's own MTD request volume against this app. */
  myRequests: number;
  /** The member's own MTD spend, USD. */
  mySpend: number;
}

export const ROUTE_META: Record<RouteProvider, RouteProviderMeta> = {
  anthropic: { color: 'var(--vx-prov-anthropic)', letter: 'A', label: 'Anthropic' },
  openai: { color: 'var(--vx-prov-openai)', letter: 'O', label: 'OpenAI' },
  google: { color: 'var(--vx-prov-google)', letter: 'G', label: 'Google' },
};

const CHAIN_SONNET: RouteHop[] = [
  { model: 'claude-sonnet-4-5', prov: 'anthropic', role: 'Primary', binding: 'Anthropic · us-east' },
  { model: 'gpt-4o', prov: 'openai', role: 'Fallback 1', binding: 'OpenAI · org-2' },
  { model: 'gemini-2.5-pro', prov: 'google', role: 'Fallback 2', binding: 'Vertex · app cred' },
];

/**
 * Apps mock. Mirrors the design source (`scrApps` / `scrAppDetail`) — the
 * built-in Chat (system), org-deployed service apps and members' personal
 * apps. Swapped for the gateway admin API in a later pass.
 */
@Injectable({ providedIn: 'root' })
export class AppsData {
  meta(prov: RouteProvider): RouteProviderMeta {
    return ROUTE_META[prov];
  }

  apps(): App[] {
    return [
      {
        id: 'app_chat',
        name: 'Chat',
        kind: 'system',
        owner: 'Vortex',
        tech: 'svc-chat',
        access: 'Whole org',
        status: 'active',
        spend: 9420,
        requests: 1_284_500,
        latency: 640,
        errRate: 0.18,
        policy: 'claude-sonnet-4-5 → gpt-4o',
        grants: [
          { who: 'Whole org', principalType: 'team', role: 'app_member', via: 'all 142 members' },
          { who: 'Platform', principalType: 'team', role: 'app_admin', via: 'team grant' },
          { who: 'Dana Cho', principalType: 'member', role: 'app_admin', via: 'direct' },
        ],
        keys: [
          {
            name: 'default',
            kind: 'default',
            mask: 'vtx_live_••••e740',
            status: 'active',
            rules: 'sonnet, gpt-4o',
            rate: '6,000 RPM',
            created: 'Jan 12',
            lastUsed: 'now',
          },
          {
            name: 'edge-cache',
            kind: 'personal',
            mask: 'vtx_live_••••11ac',
            status: 'active',
            rules: 'sonnet only',
            rate: '2,000 RPM',
            created: 'Mar 03',
            lastUsed: '2m ago',
          },
        ],
        routing: CHAIN_SONNET,
        usageByMember: [
          { label: 'Dana Cho', value: 3960 },
          { label: 'Priya Raman', value: 2260 },
          { label: 'Marcus Reed', value: 1510 },
          { label: 'Leo Martins', value: 940 },
          { label: 'Wei Zhang', value: 750 },
        ],
        usageByModel: [
          { label: 'claude-sonnet-4-5', value: 5560, prov: 'anthropic' },
          { label: 'gpt-4o', value: 2830, prov: 'openai' },
          { label: 'gemini-2.5-pro', value: 1030, prov: 'google' },
        ],
      },
      {
        id: 'app_support',
        name: 'Support Copilot',
        kind: 'service',
        owner: 'Priya Raman',
        tech: 'svc-support',
        access: 'Data Science, Mobile',
        status: 'active',
        spend: 6240,
        requests: 742_100,
        latency: 810,
        errRate: 0.42,
        policy: 'gpt-4o → claude-haiku-4-5',
        grants: [
          { who: 'Data Science', principalType: 'team', role: 'app_member', via: 'team grant' },
          { who: 'Mobile', principalType: 'team', role: 'app_member', via: 'team grant' },
          { who: 'Priya Raman', principalType: 'member', role: 'app_admin', via: 'direct' },
        ],
        keys: [
          {
            name: 'default',
            kind: 'default',
            mask: 'vtx_live_••••2b8c',
            status: 'active',
            rules: 'gpt-4o, haiku',
            rate: '2,000 RPM',
            created: 'Feb 08',
            lastUsed: '3m ago',
          },
        ],
        routing: [
          { model: 'gpt-4o', prov: 'openai', role: 'Primary', binding: 'OpenAI · org-2' },
          { model: 'claude-haiku-4-5', prov: 'anthropic', role: 'Fallback 1', binding: 'Anthropic · us-east' },
        ],
        usageByMember: [
          { label: 'Priya Raman', value: 2620 },
          { label: 'Aisha Khan', value: 1500 },
          { label: 'Leo Martins', value: 1000 },
          { label: 'Wei Zhang', value: 620 },
          { label: 'Sara Okafor', value: 500 },
        ],
        usageByModel: [
          { label: 'gpt-4o', value: 4370, prov: 'openai' },
          { label: 'claude-haiku-4-5', value: 1870, prov: 'anthropic' },
        ],
      },
      {
        id: 'app_analytics',
        name: 'Analytics ETL',
        kind: 'service',
        owner: 'Dana Cho',
        tech: 'svc-analytics',
        access: 'Platform',
        status: 'active',
        spend: 4100,
        requests: 318_900,
        latency: 1240,
        errRate: 0.9,
        policy: 'gemini-2.5-pro',
        grants: [
          { who: 'Platform', principalType: 'team', role: 'app_member', via: 'team grant' },
          { who: 'Dana Cho', principalType: 'member', role: 'app_admin', via: 'direct' },
        ],
        keys: [
          {
            name: 'default',
            kind: 'default',
            mask: 'vtx_live_••••7d51',
            status: 'active',
            rules: 'gemini',
            rate: '1,000 RPM',
            created: 'Jan 30',
            lastUsed: '8m ago',
          },
          {
            name: 'legacy',
            kind: 'personal',
            mask: 'vtx_live_••••99ab',
            status: 'stale',
            rules: 'gemini',
            rate: '1,000 RPM',
            created: 'Nov 04',
            lastUsed: '3mo ago',
          },
        ],
        routing: [
          { model: 'gemini-2.5-pro', prov: 'google', role: 'Primary', binding: 'Vertex · app cred' },
        ],
        usageByMember: [
          { label: 'Dana Cho', value: 1720 },
          { label: 'Marcus Reed', value: 980 },
          { label: 'Priya Raman', value: 660 },
          { label: 'Wei Zhang', value: 410 },
          { label: 'Sara Okafor', value: 330 },
        ],
        usageByModel: [{ label: 'gemini-2.5-pro', value: 4100, prov: 'google' }],
      },
      {
        id: 'app_playground',
        name: 'Leo’s Playground',
        kind: 'personal',
        owner: 'Leo Martins',
        tech: '—',
        access: 'Leo Martins',
        status: 'active',
        spend: 180,
        requests: 12_400,
        latency: 590,
        errRate: 0.1,
        policy: 'claude-sonnet-4-5',
        grants: [{ who: 'Leo Martins', principalType: 'member', role: 'app_admin', via: 'direct' }],
        keys: [
          {
            name: 'default',
            kind: 'default',
            mask: 'vtx_live_••••55af',
            status: 'active',
            rules: 'All models',
            rate: '600 RPM',
            created: 'Apr 19',
            lastUsed: '5m ago',
          },
        ],
        routing: [
          { model: 'claude-sonnet-4-5', prov: 'anthropic', role: 'Primary', binding: 'owner keys' },
        ],
        usageByMember: [{ label: 'Leo Martins', value: 180 }],
        usageByModel: [{ label: 'claude-sonnet-4-5', value: 180, prov: 'anthropic' }],
      },
      {
        id: 'app_notebook',
        name: 'Research Notebook',
        kind: 'personal',
        owner: 'Wei Zhang',
        tech: '—',
        access: 'Wei Zhang',
        status: 'paused',
        spend: 210,
        requests: 9_800,
        latency: 720,
        errRate: 0.0,
        policy: 'claude-haiku-4-5',
        grants: [{ who: 'Wei Zhang', principalType: 'member', role: 'app_admin', via: 'direct' }],
        keys: [
          {
            name: 'default',
            kind: 'default',
            mask: 'vtx_live_••••cf20',
            status: 'active',
            rules: 'All models',
            rate: '600 RPM',
            created: 'Feb 22',
            lastUsed: '1w ago',
          },
        ],
        routing: [
          { model: 'claude-haiku-4-5', prov: 'anthropic', role: 'Primary', binding: 'owner keys' },
        ],
        usageByMember: [{ label: 'Wei Zhang', value: 210 }],
        usageByModel: [{ label: 'claude-haiku-4-5', value: 210, prov: 'anthropic' }],
      },
    ];
  }

  /**
   * Apps the signed-in member can use — the built-in Chat, service apps they're
   * granted, and their own personal apps. Read-only for `app_member`; an
   * `app_admin` (owner) may configure. Mirrors the design's `scrMyApps`.
   */
  myApps(): MemberApp[] {
    return [
      {
        id: 'app_chat',
        name: 'Chat',
        kind: 'system',
        policy: 'claude-sonnet-4-5 → gpt-4o',
        role: 'app_member',
        can: 'Use the built-in chat',
        myRequests: 8_420,
        mySpend: 96,
      },
      {
        id: 'app_support',
        name: 'Support Copilot',
        kind: 'service',
        policy: 'gpt-4o → claude-haiku-4-5',
        role: 'app_member',
        can: 'Send requests via the granted key',
        myRequests: 21_400,
        mySpend: 312,
      },
      {
        id: 'app_notebook',
        name: 'Research Notebook',
        kind: 'personal',
        policy: 'claude-haiku-4-5',
        role: 'app_admin',
        can: 'Configure routing, access & keys',
        myRequests: 9_800,
        mySpend: 210,
      },
    ];
  }

  /** Owner options for the Deploy-app modal (active humans). */
  ownerOptions(): string[] {
    return ['Dana Cho', 'Priya Raman', 'Leo Martins', 'Wei Zhang', 'Sara Okafor', 'Marcus Reed'];
  }

  /** Teams a service account can sit in. */
  teamOptions(): string[] {
    return ['Platform', 'Data Science', 'Mobile', 'Research', 'Finance'];
  }

  /** Default routing policy presets. */
  policyOptions(): string[] {
    return ['claude-sonnet-4-5 → gpt-4o', 'gpt-4o only', 'Cost-optimized (haiku / mini)'];
  }
}
