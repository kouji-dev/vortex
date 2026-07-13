import { test, expect, request, type APIRequestContext } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { resetAll } from "./reset";
import { MULTI_BASE, withDb } from "./helpers";

const BASE = process.env.E2E_BASE ?? "http://localhost:8080";
const ORIGIN = { origin: "http://localhost:4200" };

// fresh single-org state (DB + Redis buckets) before each test →
// first signup = owner, next = member
test.beforeEach(async () => {
  await resetAll();
});

type Prov = {
  member: {
    membershipId: string;
    orgId: string;
    role: string;
    teamId: string;
    teamRole: string | null;
  };
  defaultKey: string;
};

async function signUpAndProvision(): Promise<{ ctx: APIRequestContext; prov: Prov }> {
  const ctx = await request.newContext();
  const email = `e2e+${Date.now()}-${Math.floor(Math.random() * 1e6)}@acme.test`;
  await ctx.post(`${BASE}/api/auth/sign-up/email`, {
    headers: ORIGIN,
    data: { name: "E2E", email, password: "changeme123" },
  });
  const prov = (await (
    await ctx.post(`${BASE}/api/provision`, { data: {} })
  ).json()) as Prov;
  return { ctx, prov };
}

// ── /me requires auth (401 signed out; 200 with user when signed in) ─────────

test("GET /me is 401 when signed out", async ({ request }) => {
  const r = await request.get(`${BASE}/api/me`);
  expect(r.status()).toBe(401);
});

test("GET /me returns the current user when signed in", async () => {
  const { ctx } = await signUpAndProvision();
  const r = await ctx.get(`${BASE}/api/me`);
  expect(r.status()).toBe(200);
  const body = await r.json();
  expect(body.user?.id).toBeTruthy();
  expect(body.member?.role).toBe("owner");
  expect(body.needsProvision).toBe(false);
});

// ── Teams: PATCH = org owner/admin OR this team's team_admin ──────────────────

test("team PATCH: owner may edit the team", async () => {
  const { ctx, prov } = await signUpAndProvision();
  const r = await ctx.patch(`${BASE}/api/teams/${prov.member.teamId}`, {
    data: { name: "Owner Renamed" },
  });
  expect(r.status()).toBe(200);
  expect((await r.json()).name).toBe("Owner Renamed");
});

test("team PATCH: a plain member of the team is forbidden (403)", async () => {
  const owner = await signUpAndProvision(); // seat 1 = owner
  const memberSess = await signUpAndProvision(); // seat 2 = member
  expect(memberSess.prov.member.role).toBe("member");

  const r = await memberSess.ctx.patch(
    `${BASE}/api/teams/${memberSess.prov.member.teamId}`,
    { data: { name: "Member Renamed" } },
  );
  expect(r.status()).toBe(403);
  // untouched
  const team = await (
    await owner.ctx.get(`${BASE}/api/teams`)
  ).json();
  expect(team.items[0].name).not.toBe("Member Renamed");
});

test("team PATCH: a promoted team_admin (org member) may edit the team", async () => {
  const owner = await signUpAndProvision();
  const memberSess = await signUpAndProvision();
  const teamId = memberSess.prov.member.teamId;
  const memberId = memberSess.prov.member.membershipId;

  // owner promotes the member to team_admin of that team
  const promote = await owner.ctx.patch(`${BASE}/api/members/${memberId}`, {
    data: { teamRole: "team_admin" },
  });
  expect(promote.status()).toBe(200);
  expect((await promote.json()).teamRole).toBe("team_admin");

  // now the member (still org-level "member") may edit their own team
  const r = await memberSess.ctx.patch(`${BASE}/api/teams/${teamId}`, {
    data: { name: "TeamAdmin Renamed" },
  });
  expect(r.status()).toBe(200);
  expect((await r.json()).name).toBe("TeamAdmin Renamed");
});

// ── Apps: manage-access = org owner/admin OR app owner / app_admin ────────────

test("app access: the app owner (a member) may grant access", async () => {
  const owner = await signUpAndProvision();
  const memberSess = await signUpAndProvision();

  // the member creates a service app → becomes its ownerMemberId
  const created = await memberSess.ctx.post(`${BASE}/api/apps`, {
    data: { name: "Member App", kind: "service" },
  });
  expect(created.status()).toBe(201);
  const appId = (await created.json()).id;

  // owner of the app may grant access even though they are only an org "member"
  const grant = await memberSess.ctx.post(`${BASE}/api/apps/${appId}/access`, {
    data: {
      principalType: "member",
      principalId: owner.prov.member.membershipId,
      role: "app_member",
    },
  });
  expect(grant.status()).toBe(201);
});

test("app access: a member with no ownership/grant is forbidden (403)", async () => {
  const owner = await signUpAndProvision();
  const memberSess = await signUpAndProvision();

  // owner creates an app the member neither owns nor is granted admin on
  const created = await owner.ctx.post(`${BASE}/api/apps`, {
    data: { name: "Owner App", kind: "service" },
  });
  expect(created.status()).toBe(201);
  const appId = (await created.json()).id;

  const grant = await memberSess.ctx.post(`${BASE}/api/apps/${appId}/access`, {
    data: {
      principalType: "member",
      principalId: memberSess.prov.member.membershipId,
      role: "app_member",
    },
  });
  expect(grant.status()).toBe(403);
});

// ── Keys: minting for others, rules validation, admin list/revoke ─────────────

test("keys: a member may not mint a key for the admin; an admin may mint for a member", async () => {
  const owner = await signUpAndProvision();
  const memberSess = await signUpAndProvision();

  // member → key owned by the owner: management action → 403
  const forbidden = await memberSess.ctx.post(`${BASE}/api/keys`, {
    data: { ownerMemberId: owner.prov.member.membershipId },
  });
  expect(forbidden.status()).toBe(403);

  // owner → key owned by the member: allowed
  const minted = await owner.ctx.post(`${BASE}/api/keys`, {
    data: { ownerMemberId: memberSess.prov.member.membershipId },
  });
  expect(minted.status()).toBe(201);
  const body = await minted.json();
  expect(body.key).toMatch(/^vtx_/);
});

test("keys: invalid CIDR rule and past expiresAt are rejected (400)", async () => {
  const { ctx } = await signUpAndProvision();

  const badCidr = await ctx.post(`${BASE}/api/keys`, {
    data: { rules: [{ ruleType: "ip_cidrs", ruleValue: ["999.1.2.3/33"] }] },
  });
  expect(badCidr.status()).toBe(400);

  const pastExpiry = await ctx.post(`${BASE}/api/keys`, {
    data: { expiresAt: "2020-01-01T00:00:00.000Z" },
  });
  expect(pastExpiry.status()).toBe(400);
});

test("keys: admin lists a member's keys and a revoked key stops working on /v1", async () => {
  const owner = await signUpAndProvision();
  const memberSess = await signUpAndProvision();
  const memberId = memberSess.prov.member.membershipId;

  // admin filter by member
  const list = await owner.ctx.get(`${BASE}/api/keys?memberId=${memberId}`);
  expect(list.status()).toBe(200);
  const { items } = await list.json();
  expect(items.length).toBeGreaterThanOrEqual(1);
  for (const k of items) expect(k.ownerMemberId).toBe(memberId);

  // member's key works before revocation…
  const before = await memberSess.ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${memberSess.prov.defaultKey}` },
    data: { model: "openai/gpt-4o-mini", messages: [{ role: "user", content: "hi" }] },
  });
  expect(before.status()).toBe(200);

  // …admin revokes it → 401 on the gateway
  const revoke = await owner.ctx.post(`${BASE}/api/keys/${items[0].id}/revoke`, {
    data: {},
  });
  expect(revoke.status()).toBe(200);
  const after = await memberSess.ctx.post(`${BASE}/v1/chat/completions`, {
    headers: { authorization: `Bearer ${memberSess.prov.defaultKey}` },
    data: { model: "openai/gpt-4o-mini", messages: [{ role: "user", content: "hi" }] },
  });
  expect(after.status()).toBe(401);
});

// ── Members: last-owner guard + directory redaction ───────────────────────────

test("members: demoting the last remaining owner is a 409 conflict", async () => {
  const { ctx, prov } = await signUpAndProvision();
  const r = await ctx.patch(`${BASE}/api/members/${prov.member.membershipId}`, {
    data: { role: "member" },
  });
  expect(r.status()).toBe(409);
  expect((await r.json()).error).toBe("last_owner");
});

test("members: budget override is manager-only data — hidden from plain members", async () => {
  const owner = await signUpAndProvision();
  const memberSess = await signUpAndProvision();

  const managerView = await (await owner.ctx.get(`${BASE}/api/members`)).json();
  expect(managerView.items.length).toBeGreaterThanOrEqual(2);
  expect("budgetOverrideMicro" in managerView.items[0]).toBe(true);

  const memberView = await (
    await memberSess.ctx.get(`${BASE}/api/members`)
  ).json();
  expect(memberView.items.length).toBeGreaterThanOrEqual(2);
  for (const m of memberView.items) {
    expect("budgetOverrideMicro" in m).toBe(false);
  }
});

// ── Team budgets + team lifecycle ─────────────────────────────────────────────

test("team budget: team_admin may not set it (403); org admin may (200); team DELETE works", async () => {
  const owner = await signUpAndProvision();
  const memberSess = await signUpAndProvision();
  const teamId = memberSess.prov.member.teamId;

  // promote the member to team_admin of their team
  const promote = await owner.ctx.patch(
    `${BASE}/api/members/${memberSess.prov.member.membershipId}`,
    { data: { teamRole: "team_admin" } },
  );
  expect(promote.status()).toBe(200);

  // team_admin (org member) may NOT touch the team budget
  const denied = await memberSess.ctx.patch(
    `${BASE}/api/budgets/team/${teamId}`,
    { data: { budgetMicro: 1_000_000 } },
  );
  expect(denied.status()).toBe(403);

  // org owner/admin may
  const allowed = await owner.ctx.patch(`${BASE}/api/budgets/team/${teamId}`, {
    data: { budgetMicro: 1_000_000 },
  });
  expect(allowed.status()).toBe(200);

  // team DELETE (create a scratch team so the default team stays intact)
  const created = await owner.ctx.post(`${BASE}/api/teams`, {
    data: { name: "Scratch Team" },
  });
  expect(created.status()).toBe(201);
  const scratchId = (await created.json()).id;
  const del = await owner.ctx.delete(`${BASE}/api/teams/${scratchId}`);
  expect(del.status()).toBe(200);
  expect((await del.json()).ok).toBe(true);
});

// ── Platform (multi server): support role is read-only ────────────────────────

test("platform: a support-role admin can read tenants but mutations are 403", async () => {
  // fresh user on the multi server; seeded directly as a `support` platform admin
  const ctx = await request.newContext();
  const email = `e2e+support${Date.now()}-${Math.floor(Math.random() * 1e6)}@acme.test`;
  await ctx.post(`${MULTI_BASE}/api/auth/sign-up/email`, {
    headers: ORIGIN,
    data: { name: "Support", email, password: "changeme123" },
  });
  const me = await (await ctx.get(`${MULTI_BASE}/api/me`)).json();
  const userId = me.user.id as string;
  await withDb(
    (sql) =>
      sql`insert into platform_admins (id, user_id, role)
          values (${randomUUID()}, ${userId}, 'support')`,
  );

  // read allowed
  const read = await ctx.get(`${MULTI_BASE}/platform/tenants`);
  expect(read.status()).toBe(200);

  // mutations denied for support
  const provision = await ctx.post(`${MULTI_BASE}/platform/tenants`, {
    data: { name: "Nope Inc" },
  });
  expect(provision.status()).toBe(403);

  const plan = await ctx.post(`${MULTI_BASE}/platform/plans`, {
    data: { name: "Nope Plan" },
  });
  expect(plan.status()).toBe(403);

  const suspend = await ctx.post(
    `${MULTI_BASE}/platform/tenants/some-org-id/suspend`,
    { data: {} },
  );
  expect(suspend.status()).toBe(403);
});
