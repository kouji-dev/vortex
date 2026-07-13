import type { CatalogModel, HostModel, SupportedFeatures } from './catalog.service';

// ── formatters ───────────────────────────────────────────────
/** micro-USD per 1k tokens → "$X.XX" per 1M tokens. */
export function money1M(micro: number | undefined): string {
  if (micro == null) return '—';
  if (micro === 0) return '$0.00';
  return `$${(micro / 1000).toFixed(2)}`;
}

export function fmtCtx(n: number | undefined): string {
  if (n == null) return '—';
  if (n >= 1_000_000) return `${+(n / 1_000_000).toFixed(n % 1_000_000 ? 1 : 0)}M`;
  if (n >= 1000) return `${Math.round(n / 1000)}K`;
  return String(n);
}

// ── provider avatar initials ─────────────────────────────────
const PMARK: Record<string, string> = {
  azure: 'Az',
  bedrock: 'Bk',
  vertex: 'Vx',
  together: 'Tg',
  fireworks: 'Fw',
  deepseek: 'Ds',
  xai: 'x',
};
export function pmark(hostId: string): string {
  return PMARK[hostId] ?? (hostId[0] ?? '?').toUpperCase();
}

// ── capabilities (order + label + inline icon path) ──────────
export interface CapDef {
  key: keyof SupportedFeatures;
  label: string;
  /** inner markup of a 24×24 stroke=currentColor icon. */
  svg: string;
}
export const CAPS: CapDef[] = [
  { key: 'tools', label: 'Tools', svg: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L4 17v3h3l5.3-5.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2-2 2.5-2.5Z"/>' },
  { key: 'vision', label: 'Vision', svg: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z"/><circle cx="12" cy="12" r="2.5"/>' },
  { key: 'reasoning', label: 'Reasoning', svg: '<path d="M12 3l1.9 4.1L18 9l-4.1 1.9L12 15l-1.9-4.1L6 9l4.1-1.9L12 3Z"/><path d="M18 15l.9 2 2 .9-2 .9-.9 2-.9-2-2-.9 2-.9.9-2Z"/>' },
  { key: 'streaming', label: 'Streaming', svg: '<path d="M3 12h4l2-6 4 12 2-6h6"/>' },
  { key: 'jsonSchema', label: 'JSON', svg: '<path d="M8 4C6 4 6 6 6 8s0 4-2 4c2 0 2 2 2 4s0 4 2 4"/><path d="M16 4c2 0 2 2 2 4s0 4 2 4c-2 0-2 2-2 4s0 4-2 4"/>' },
  { key: 'caching', label: 'Caching', svg: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>' },
  { key: 'webSearch', label: 'Web', svg: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>' },
];

// ── model-level aggregation across hosts ─────────────────────
export function modelFeatures(m: CatalogModel): SupportedFeatures {
  const f: SupportedFeatures = {};
  for (const h of m.hosts)
    for (const k of Object.keys(h.supportedFeatures ?? {}) as (keyof SupportedFeatures)[])
      if (h.supportedFeatures?.[k]) f[k] = true;
  return f;
}
export function modelOpenWeights(m: CatalogModel): boolean {
  return m.hosts.some((h) => h.openWeights);
}
export function cheapestInput(m: CatalogModel): number {
  return Math.min(...m.hosts.map((h) => h.inputPer1kMicro));
}
export function isCheapest(m: CatalogModel, h: HostModel): boolean {
  return m.hosts.length > 1 && h.inputPer1kMicro === cheapestInput(m);
}

// ── filter state + predicate ─────────────────────────────────
export interface FilterState {
  q: string;
  mod: 'all' | 'text' | 'multimodal' | 'embedding';
  caps: (keyof SupportedFeatures)[];
}
export const emptyFilter = (): FilterState => ({ q: '', mod: 'all', caps: [] });

// ── sorting ──────────────────────────────────────────────────
export type SortKey = 'newest' | 'price' | 'intelligence' | 'effective';
export const SORTS: { key: SortKey; label: string }[] = [
  { key: 'newest', label: 'Newest' },
  { key: 'price', label: 'Cheapest' },
  { key: 'intelligence', label: 'Intelligence' },
  { key: 'effective', label: 'Best value' },
];

/** Blended price (micro/1k): 75% input + 25% output — the ~typical usage ratio. */
export const blendedMicro = (h: HostModel): number =>
  0.75 * h.inputPer1kMicro + 0.25 * h.outputPer1kMicro;

/** nulls always sort last; otherwise numeric compare in `dir` (1 asc, -1 desc). */
function cmpNum(a: number | null, b: number | null, dir: number): number {
  if (a === b) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return (a - b) * dir;
}

/** Sort per-provider table rows ({ host row + model intelligence }) by a key. */
export function sortRows<T extends { h: HostModel; intel: number | null; id: string }>(
  rows: T[],
  key: SortKey,
): T[] {
  const out = [...rows];
  switch (key) {
    case 'price':
      out.sort((a, b) => cmpNum(blendedMicro(a.h), blendedMicro(b.h), 1) || a.id.localeCompare(b.id));
      break;
    case 'intelligence':
      out.sort((a, b) => cmpNum(a.intel, b.intel, -1) || a.id.localeCompare(b.id));
      break;
    case 'effective':
      out.sort((a, b) => {
        const ea = a.intel && a.intel > 0 ? blendedMicro(a.h) / a.intel : null;
        const eb = b.intel && b.intel > 0 ? blendedMicro(b.h) / b.intel : null;
        return cmpNum(ea, eb, 1) || a.id.localeCompare(b.id);
      });
      break;
    default:
      out.sort((a, b) => {
        const ra = a.h.releaseDate ?? '';
        const rb = b.h.releaseDate ?? '';
        if (ra === rb) return a.id.localeCompare(b.id);
        return ra && rb ? rb.localeCompare(ra) : ra ? -1 : 1;
      });
  }
  return out;
}

export function matchesFilters(m: CatalogModel, s: FilterState): boolean {
  if (s.mod !== 'all' && m.modality !== s.mod) return false;
  if (s.caps.length) {
    const f = modelFeatures(m);
    if (!s.caps.every((k) => f[k])) return false;
  }
  const q = s.q.trim().toLowerCase();
  if (q) {
    const hay =
      m.displayName.toLowerCase() +
      ' ' +
      m.id.toLowerCase() +
      ' ' +
      m.hosts.map((h) => h.upstreamModelId.toLowerCase()).join(' ');
    if (!hay.includes(q)) return false;
  }
  return true;
}
