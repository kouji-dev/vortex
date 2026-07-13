import { defineConfig } from "@playwright/test";

// Spins up the mock provider + mock Stripe + TWO API instances, then runs the
// API/gateway E2E suite. `pnpm test:e2e`.
//   :8080 — single-tenant, self-hosted   (authz / gateway / budgets / seats)
//   :8081 — multi-tenant, managed + Stripe (billing plane: webhooks, credits, DLQ)
// Both share the same Postgres + Redis (docker compose, ports 5433/6380).
// Ports are env-driven so parallel worktrees don't collide: set API_PORT_E2E /
// MOCK_PORT_E2E (defaults 8080 / 9099).
//
// LANDING UI suite (browser): opt-in via `playwright test --project=landing`
// (or LANDING_E2E=1). It boots ONLY `ng serve landing` (catalog is stubbed via
// page.route) — default/API-only runs are completely unaffected: no landing
// project, no Angular dev server.
const API_PORT = process.env.API_PORT_E2E ?? "8080";
const MOCK_PORT = process.env.MOCK_PORT_E2E ?? "9099";
const MOCK_URL = `http://localhost:${MOCK_PORT}`;
const LANDING_PORT = process.env.LANDING_PORT_E2E ?? "4401";
const LANDING_URL = `http://127.0.0.1:${LANDING_PORT}`;

// Which projects were requested on the CLI (`--project foo` / `--project=foo`).
const requestedProjects: string[] = [];
process.argv.forEach((a, i) => {
  if (a === "--project") requestedProjects.push(process.argv[i + 1] ?? "");
  else if (a.startsWith("--project=")) requestedProjects.push(a.slice("--project=".length));
});
const runLanding =
  process.env.LANDING_E2E === "1" || requestedProjects.includes("landing");
const landingOnly =
  process.env.LANDING_E2E_ONLY === "1" ||
  (runLanding && requestedProjects.length > 0 && requestedProjects.every((p) => p === "landing"));
// Worker processes re-evaluate this config WITHOUT the CLI args — propagate
// the decision through the environment so the project set stays identical.
if (runLanding) process.env.LANDING_E2E = "1";
if (landingOnly) process.env.LANDING_E2E_ONLY = "1";

const landingServer = {
  command: `pnpm exec ng serve landing --configuration development --port ${LANDING_PORT} --host 127.0.0.1`,
  url: LANDING_URL,
  reuseExistingServer: false,
  timeout: 240_000,
};

const apiServers = [
    {
      command: "node e2e/mock-provider.mjs",
      url: `${MOCK_URL}/models`,
      reuseExistingServer: false,
      timeout: 20_000,
      env: { MOCK_DELAY_MS: "150", MOCK_PORT },
    },
    {
      command: "node e2e/mock-stripe.mjs",
      url: "http://localhost:9098/health",
      reuseExistingServer: false,
      timeout: 20_000,
    },
    {
      command: "node --import tsx apps/api/src/server.ts",
      url: `http://localhost:${API_PORT}/health`,
      reuseExistingServer: false,
      timeout: 40_000,
      env: {
        PORT: API_PORT,
        OPENAI_BASE_URL: MOCK_URL,
        OPENAI_API_KEY: "test-mock",
        // Point an OpenAI-compatible provider (Groq) at the same mock so the
        // registry/provider-prefix routing is covered E2E.
        GROQ_BASE_URL: MOCK_URL,
        GROQ_API_KEY: "test-mock",
        // Extra hosts pointed at the mock so the (family, host) forwarding E2E can
        // drive Anthropic-direct + Bedrock (Anthropic envelope) through one mock.
        ANTHROPIC_BASE_URL: MOCK_URL,
        ANTHROPIC_API_KEY: "test-mock",
        AWS_BEDROCK_BASE_URL: MOCK_URL,
        AWS_BEDROCK_API_KEY: "test-mock",
        AWS_BEDROCK_REGION: "us-east-1",
        TENANCY_MODE: "single",
        // Small upstream timeouts so the hang → 504 test is fast.
        UPSTREAM_CONNECT_TIMEOUT_MS: "2500",
        UPSTREAM_TOTAL_TIMEOUT_MS: "2500",
        DLQ_SWEEP_MS: "1500",
      },
    },
    {
      command: "node --import tsx apps/api/src/server.ts",
      url: "http://localhost:8081/health",
      reuseExistingServer: false,
      timeout: 40_000,
      env: {
        PORT: "8081",
        TENANCY_MODE: "multi",
        DEPLOYMENT_MODE: "managed",
        BETTER_AUTH_URL: "http://localhost:8081",
        OPENAI_BASE_URL: MOCK_URL,
        OPENAI_API_KEY: "test-mock",
        // Stripe billing plane against the local mock; webhook events are
        // signed by the specs with this secret (real signature verification).
        STRIPE_SECRET_KEY: "sk_test_mock",
        STRIPE_WEBHOOK_SECRET: "whsec_e2e_test_secret",
        STRIPE_API_BASE: "http://localhost:9098",
        UPSTREAM_CONNECT_TIMEOUT_MS: "2500",
        UPSTREAM_TOTAL_TIMEOUT_MS: "2500",
        DLQ_SWEEP_MS: "1500",
      },
    },
];

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  projects: [
    // API/gateway suite — request-level specs, no browser. Unchanged default.
    ...(landingOnly
      ? []
      : [{ name: "api", testIgnore: /landing\.spec\.ts/ }]),
    // Landing UI suite — real Chromium against `ng serve landing`.
    ...(runLanding
      ? [
          {
            name: "landing",
            testMatch: /landing\.spec\.ts/,
            use: {
              baseURL: LANDING_URL,
              permissions: ["clipboard-read", "clipboard-write"],
            },
          },
        ]
      : []),
  ],
  webServer: landingOnly
    ? [landingServer]
    : runLanding
      ? [...apiServers, landingServer]
      : apiServers,
});
