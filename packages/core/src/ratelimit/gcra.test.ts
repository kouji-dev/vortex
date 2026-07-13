import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

// Replace the singleton ioredis client with an in-memory mock (fengari Lua VM)
// so the real Lua scripts run without a Redis server.
vi.mock("../redis.js", async () => {
  const { default: RedisMock } = await import("ioredis-mock");
  return {
    redis: new (RedisMock as unknown as new () => object)(),
    budgetKey: (...parts: string[]) => parts.join(":"),
  };
});

const { gcra, gcraRefund } = await import("./gcra.js");
const { redis } = (await import("../redis.js")) as unknown as {
  redis: { flushall: () => Promise<unknown> };
};

// limit 10/min → T = 6000ms, tau (burst) = 60000ms
const OPTS = { limit: 10, periodMs: 60_000 };

let key = "";
let n = 0;

describe("gcra", () => {
  beforeEach(async () => {
    await redis.flushall();
    key = `rl:test:${n++}`;
    vi.useFakeTimers();
    vi.setSystemTime(1_700_000_000_000);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("admits a normal request and tracks remaining", async () => {
    const r = await gcra(key, { ...OPTS, cost: 1 });
    expect(r.allowed).toBe(true);
    expect(r.remaining).toBe(9);
  });

  it("oversized cost (2x burst) is admitted on an empty bucket", async () => {
    const r = await gcra(key, { ...OPTS, cost: 20 }); // incr = 120s > tau = 60s
    expect(r.allowed).toBe(true);
    expect(r.resetMs).toBe(120_000);
  });

  it("oversized cost is denied while the bucket is backlogged", async () => {
    const first = await gcra(key, { ...OPTS, cost: 20 });
    expect(first.allowed).toBe(true);

    // any request while the oversized debt drains is denied…
    const small = await gcra(key, { ...OPTS, cost: 1 });
    expect(small.allowed).toBe(false);
    expect(small.retryAfterMs).toBeGreaterThan(0);

    // …including another oversized one, with retryAfter = time to idle
    const second = await gcra(key, { ...OPTS, cost: 20 });
    expect(second.allowed).toBe(false);
    expect(second.retryAfterMs).toBe(120_000);

    // once the debt has drained, oversized is admitted again (no permanent 429)
    vi.setSystemTime(1_700_000_000_000 + 120_001);
    const third = await gcra(key, { ...OPTS, cost: 20 });
    expect(third.allowed).toBe(true);
  });

  it("normal costs still enforce burst capacity", async () => {
    const a = await gcra(key, { ...OPTS, cost: 10 }); // consumes full burst
    expect(a.allowed).toBe(true);
    expect(a.remaining).toBe(0);
    const b = await gcra(key, { ...OPTS, cost: 1 });
    expect(b.allowed).toBe(false);
  });

  it("refund gives capacity back", async () => {
    await gcra(key, { ...OPTS, cost: 5 }); // TAT = now + 30s
    // without a refund, a full-burst request would be denied
    const denied = await gcra(key, { ...OPTS, cost: 10 });
    expect(denied.allowed).toBe(false);
    await gcraRefund(key, { ...OPTS, delta: 5 }); // give the 5 back → TAT = now
    const ok = await gcra(key, { ...OPTS, cost: 10 });
    expect(ok.allowed).toBe(true);
  });

  it("refund clamps at now (never creates extra burst)", async () => {
    await gcra(key, { ...OPTS, cost: 1 });
    await gcraRefund(key, { ...OPTS, delta: 1_000 }); // huge over-refund
    const full = await gcra(key, { ...OPTS, cost: 10 }); // exactly one burst fits
    expect(full.allowed).toBe(true);
    const extra = await gcra(key, { ...OPTS, cost: 1 });
    expect(extra.allowed).toBe(false);
  });

  it("refund on a missing key is a no-op", async () => {
    await expect(
      gcraRefund("rl:test:missing", { ...OPTS, delta: 5 }),
    ).resolves.toBeUndefined();
  });
});
