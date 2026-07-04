import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

/** A tenant organisation as returned by GET /platform/tenants. */
export interface Tenant {
  id: string;
  name: string;
  status: 'active' | 'suspended';
  planId: string | null;
  createdAt: string;
  members: number;
  apps: number;
  spendMicro: number;
}

/** A cross-tenant usage row from GET /platform/usage. */
export interface UsageRow {
  orgId: string;
  provider: string;
  model: string;
  requests: number;
  totalTokens: number;
  costMicro: number;
}

/** A billing plan (GET/POST /platform/plans). */
export interface Plan {
  id: string;
  name: string;
  price?: number | null;
  stripePriceId?: string | null;
  limits?: Record<string, unknown> | null;
}

/** A platform (vendor) admin (GET/POST /platform/admins). */
export interface PlatformAdmin {
  id?: string;
  userId?: string;
  email: string;
  role: string;
  createdAt?: string;
}

/** A hash-chained platform audit entry (GET /platform/audit). */
export interface AuditEntry {
  id?: string;
  action: string;
  targetOrg?: string | null;
  adminEmail?: string | null;
  platformAdminId?: string | null;
  metadata?: unknown;
  prevHash?: string | null;
  entryHash?: string | null;
  createdAt?: string | null;
}

/**
 * Platform super-admin data access. Every screen goes through this
 * service — components never touch HttpClient directly (mirrors
 * apps/web's shared/data pattern). All endpoints are `/platform/*` and
 * require a platform-admin session (403 otherwise).
 */
@Injectable({ providedIn: 'root' })
export class PlatformService {
  private readonly http = inject(HttpClient);

  // ── Tenants ──
  async tenants(): Promise<Tenant[]> {
    const res = await firstValueFrom(
      this.http.get<{ tenants: Tenant[] }>('/platform/tenants'),
    );
    return res?.tenants ?? [];
  }

  async provisionTenant(name: string): Promise<void> {
    await firstValueFrom(this.http.post('/platform/tenants', { name }));
  }

  async suspendTenant(id: string): Promise<void> {
    await firstValueFrom(this.http.post(`/platform/tenants/${id}/suspend`, {}));
  }

  async reactivateTenant(id: string): Promise<void> {
    await firstValueFrom(this.http.post(`/platform/tenants/${id}/reactivate`, {}));
  }

  async deleteTenant(id: string): Promise<void> {
    await firstValueFrom(this.http.delete(`/platform/tenants/${id}`));
  }

  // ── Usage ──
  async usage(): Promise<UsageRow[]> {
    const res = await firstValueFrom(
      this.http.get<{ rows: UsageRow[] }>('/platform/usage'),
    );
    return res?.rows ?? [];
  }

  // ── Plans ──
  async plans(): Promise<Plan[]> {
    const res = await firstValueFrom(
      this.http.get<{ plans: Plan[] }>('/platform/plans'),
    );
    return res?.plans ?? [];
  }

  async createPlan(name: string, price?: number): Promise<void> {
    await firstValueFrom(this.http.post('/platform/plans', { name, price }));
  }

  // ── Platform admins ──
  async admins(): Promise<PlatformAdmin[]> {
    const res = await firstValueFrom(
      this.http.get<{ admins: PlatformAdmin[] }>('/platform/admins'),
    );
    return res?.admins ?? [];
  }

  async addAdmin(email: string, role: string): Promise<void> {
    await firstValueFrom(this.http.post('/platform/admins', { email, role }));
  }

  // ── Audit ──
  async audit(): Promise<AuditEntry[]> {
    const res = await firstValueFrom(
      this.http.get<{ entries: AuditEntry[] }>('/platform/audit'),
    );
    return res?.entries ?? [];
  }
}

/** micro-USD (1e6 = $1) → localized `$1,234.56`. */
export function formatUsd(micro: number | null | undefined): string {
  const usd = (micro ?? 0) / 1_000_000;
  return usd.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  });
}

/** Compact integer formatting (2.84M, 1.9B). */
export function formatCount(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString('en-US', {
    notation: 'compact',
    maximumFractionDigits: 1,
  });
}
