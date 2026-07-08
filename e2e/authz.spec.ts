import { test, expect, request, type APIRequestContext } from "@playwright/test";
import { resetTenants } from "./reset";

const BASE = "http://localhost:8080";
const ORIGIN = { origin: "http://localhost:4200" };

// fresh single-org state before each test → first signup = owner, next = member
test.beforeEach(async () => {
  await resetTenants();
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
  expect(team[0].name).not.toBe("Member Renamed");
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
