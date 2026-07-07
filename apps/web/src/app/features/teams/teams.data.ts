import { Injectable } from '@angular/core';

export type Enforcement = 'hard' | 'soft';
export type OrgRole = 'owner' | 'admin' | 'member';
export type TeamRole = 'team_admin' | 'member';
export type MemberType = 'human' | 'technical';
export type MemberStatus = 'active' | 'invited' | 'suspended';
export type BudgetSource = 'default' | 'override';

/** A team groups people and sets a default monthly budget per member. */
export interface Team {
  id: string;
  name: string;
  /** Default monthly budget per member (EUR). */
  def: number;
  enf: Enforcement;
  members: number;
  admin: string;
  /** Team spend, month-to-date (EUR). */
  spend: number;
}

/** A member (human or per-app service account) — belongs to exactly one team. */
export interface Member {
  name: string;
  email: string;
  type: MemberType;
  role: OrgRole;
  team: string;
  teamRole: TeamRole;
  bsrc: BudgetSource;
  /** Effective monthly budget: team default OR per-member override (EUR). */
  budget: number;
  /** Spend, month-to-date (EUR). */
  spent: number;
  status: MemberStatus;
  seen: string;
  /** Owning app, for service accounts. */
  app?: string;
}

/**
 * Teams & members demo data. Mirrors the design mockup (Northwind AI).
 * Wired to the gateway's org API in a later pass; serves realistic
 * governance data so the console renders like the design source today.
 */
@Injectable({ providedIn: 'root' })
export class TeamsService {
  readonly orgName = 'Northwind AI';

  private readonly _teams: Team[] = [
    { id: 't_plat', name: 'Platform', def: 1500, enf: 'hard', members: 14, admin: 'Dana Cho', spend: 18240 },
    { id: 't_ds', name: 'Data Science', def: 2000, enf: 'soft', members: 9, admin: 'Priya Raman', spend: 9820 },
    { id: 't_mob', name: 'Mobile', def: 800, enf: 'hard', members: 6, admin: 'Leo Martins', spend: 6140 },
    { id: 't_res', name: 'Research', def: 1200, enf: 'soft', members: 5, admin: 'Wei Zhang', spend: 3210 },
  ];

  private readonly _members: Member[] = [
    { name: 'Dana Cho', email: 'dana@northwind.ai', type: 'human', role: 'owner', team: 'Platform', teamRole: 'team_admin', bsrc: 'default', budget: 1500, spent: 1180, status: 'active', seen: 'now' },
    { name: 'Priya Raman', email: 'priya@northwind.ai', type: 'human', role: 'admin', team: 'Data Science', teamRole: 'team_admin', bsrc: 'override', budget: 3000, spent: 2410, status: 'active', seen: '12m ago' },
    { name: 'Leo Martins', email: 'leo@northwind.ai', type: 'human', role: 'admin', team: 'Mobile', teamRole: 'team_admin', bsrc: 'default', budget: 800, spent: 640, status: 'active', seen: '2h ago' },
    { name: 'Wei Zhang', email: 'wei@northwind.ai', type: 'human', role: 'member', team: 'Research', teamRole: 'team_admin', bsrc: 'default', budget: 1200, spent: 980, status: 'active', seen: '4h ago' },
    { name: 'Sara Okafor', email: 'sara@northwind.ai', type: 'human', role: 'member', team: 'Platform', teamRole: 'member', bsrc: 'default', budget: 1500, spent: 120, status: 'active', seen: '1d ago' },
    { name: 'Marcus Reed', email: 'marcus@northwind.ai', type: 'human', role: 'member', team: 'Platform', teamRole: 'member', bsrc: 'override', budget: 2500, spent: 2380, status: 'active', seen: '20m ago' },
    { name: 'Aisha Khan', email: 'aisha@northwind.ai', type: 'human', role: 'member', team: 'Mobile', teamRole: 'member', bsrc: 'default', budget: 800, spent: 0, status: 'invited', seen: '—' },
    { name: 'Tomas Berg', email: 'tomas@contractor.io', type: 'human', role: 'member', team: 'Research', teamRole: 'member', bsrc: 'default', budget: 1200, spent: 0, status: 'suspended', seen: '2w ago' },
    { name: 'svc-chat', email: 'chat@svc.northwind.ai', type: 'technical', role: 'member', team: 'Platform', teamRole: 'member', bsrc: 'override', budget: 12000, spent: 9420, status: 'active', seen: 'now', app: 'Chat' },
    { name: 'svc-support', email: 'support@svc.northwind.ai', type: 'technical', role: 'member', team: 'Data Science', teamRole: 'member', bsrc: 'override', budget: 8000, spent: 6240, status: 'active', seen: '3m ago', app: 'Support Copilot' },
  ];

  teams(): Team[] {
    return this._teams;
  }

  members(): Member[] {
    return this._members;
  }

  teamNames(): string[] {
    return this._teams.map((t) => t.name);
  }

  activeHumans(): Member[] {
    return this._members.filter((m) => m.type === 'human' && m.status === 'active');
  }

  teamOf(name: string): Team | undefined {
    return this._teams.find((t) => t.name === name);
  }
}
