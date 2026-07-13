import { defineConfig } from "@playwright/test";

// Spins up the mock provider + mock Stripe + TWO API instances, then runs the
// API/gateway E2E suite. `pnpm test:e2e`.
//   :8080 — single-tenant, self-hosted   (authz / gateway / budgets / seats)
//   :8081 — multi-tenant, managed + Stripe (billing plane: webhooks, credits, DLQ)
// Both share the same Postgres + Redis (docker compose, ports 5433/6380).
// Ports are env-driven so parallel worktrees don't collide: set API_PORT_E2E /
// MOCK_PORT_E2E (defaults 8080 / 9099).
const API_PORT = process.env.API_PORT_E2E ?? "8080";
const MOCK_PORT = process.env.MOCK_PORT_E2E ?? "9099";
const MOCK_URL = `http://localhost:${MOCK_PORT}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  webServer: [
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
  ],
});
