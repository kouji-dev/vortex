import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// Landing UI E2E — runs ONLY under `playwright test --project=landing` (see
// playwright.config.ts): boots `ng serve landing` on 127.0.0.1:$LANDING_PORT_E2E
// (default 4401), no API/DB needed. The public GET /v1/catalog the catalog
// pages fetch is stubbed per-page with the REAL code catalog (models.json) and
// the REAL long HostMeta names — so the short display-name mapping is
// exercised against exactly what the live API would send.

type HostRow = { host: string; openWeights?: boolean };
type Model = { id: string; displayName: string; modality: string; hosts: HostRow[] };

const MODELS: Model[] = JSON.parse(
  readFileSync(
    resolve(process.cwd(), "packages/core/src/providers/models.json"),
    "utf8",
  ),
) as Model[];

// Mirrors @vortex/core HOSTS (the /v1/catalog `providers` payload) — long
// names on purpose: the landing UI must render the SHORT forms instead.
const PROVIDERS = [
  { id: "openai", name: "OpenAI", defaultFamily: "openai", brandColor: "#10a37f" },
  { id: "anthropic", name: "Anthropic", defaultFamily: "anthropic", brandColor: "#cc785c" },
  { id: "google", name: "Google AI Studio", defaultFamily: "google", brandColor: "#4285f4" },
  { id: "azure", name: "Azure OpenAI", defaultFamily: "openai", brandColor: "#0078d4" },
  { id: "bedrock", name: "AWS Bedrock", defaultFamily: "anthropic", brandColor: "#ff9900" },
  { id: "vertex", name: "Google Vertex AI", defaultFamily: "google", brandColor: "#34a853" },
  { id: "groq", name: "Groq", defaultFamily: "openai", brandColor: "#f55036" },
  { id: "mistral", name: "Mistral AI", defaultFamily: "openai", brandColor: "#ff7000" },
  { id: "deepseek", name: "DeepSeek", defaultFamily: "openai", brandColor: "#4d6bfe" },
  { id: "xai", name: "xAI", defaultFamily: "openai", brandColor: "#a7adba" },
  { id: "together", name: "Together AI", defaultFamily: "openai", brandColor: "#1668ff" },
  { id: "fireworks", name: "Fireworks AI", defaultFamily: "openai", brandColor: "#ff5b2e" },
];

/** Short names the UI must show (mirrors catalog.util providerDisplayName). */
const SHORT: Record<string, string> = {
  openai: "OpenAI", anthropic: "Anthropic", google: "Google", azure: "Azure",
  bedrock: "Bedrock", vertex: "Vertex", groq: "Groq", mistral: "Mistral",
  deepseek: "DeepSeek", xai: "xAI", together: "Together", fireworks: "Fireworks",
};

async function stubCatalog(page: Page): Promise<void> {
  await page.route("**/v1/catalog", (route) =>
    route.fulfill({ json: { models: MODELS, providers: PROVIDERS } }),
  );
}

// ── home ─────────────────────────────────────────────────────────────────────

test("home renders hero, teaser, marquee and three-steps", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("h1.hero-h1")).toContainText("Every model.");
  await expect(page.locator("h1.hero-h1")).toContainText("One gateway.");

  // Models & Providers teaser
  await expect(page.locator(".ct2-title")).toContainText("One logical model.");

  // provider marquee present, with pills inside
  await expect(page.locator(".ct2-marquee")).toBeVisible();
  const pills = page.locator(".ct2-pill");
  expect(await pills.count()).toBeGreaterThan(0);

  // "Three steps" section
  await expect(
    page.locator("h2", { hasText: "Three steps to shipped." }),
  ).toHaveCount(1);
});

// ── code showcase ────────────────────────────────────────────────────────────

test("code showcase: tab switch .env → TypeScript swaps the pane", async ({ page }) => {
  await page.goto("/");

  const active = page.locator(".cs-pane.on");
  await expect(active).toContainText("ANTHROPIC_BASE_URL");

  // No hydration/event-replay on this app: retry click+assert until the CSR
  // app has bootstrapped and the tab actually switches.
  const tsTab = page.locator(".cs-tab", { hasText: "TypeScript" });
  await expect(async () => {
    await tsTab.click();
    await expect(active).toContainText('import OpenAI from "openai"', { timeout: 1_000 });
  }).toPass();
  await expect(active).not.toContainText("ANTHROPIC_BASE_URL");
});

test("code showcase: copy button writes clipboard and shows copied state", async ({ page }) => {
  await page.goto("/");

  const copyBtn = page.locator(".cs-copy");
  await expect(async () => {
    await copyBtn.click();
    await expect(copyBtn).toContainText("Copied", { timeout: 1_000 });
  }).toPass();

  // clipboard-read permission is granted in the landing project config
  const clip = await page.evaluate(() => navigator.clipboard.readText());
  expect(clip).toContain("ANTHROPIC_BASE_URL=https://gateway.vortex.ai");
});

// ── catalog ──────────────────────────────────────────────────────────────────

test("catalog loads provider cards with short display names", async ({ page }) => {
  await stubCatalog(page);
  await page.goto("/models");

  const cards = page.locator(".pcard");
  await expect(cards).toHaveCount(PROVIDERS.length);
  expect(await cards.count()).toBeGreaterThan(0);

  const names = await page.locator(".pcard-name").allTextContents();
  for (const p of PROVIDERS) expect(names).toContain(SHORT[p.id]);
  // long API names never render
  await expect(page.locator("text=AWS Bedrock")).toHaveCount(0);
  await expect(page.locator("text=Google Vertex AI")).toHaveCount(0);
});

test("provider detail: open-weights switch filters and sort dropdown present", async ({ page }) => {
  // `together` serves a MIX of open-weights and closed models → deterministic filter.
  const served = MODELS.filter((m) => m.hosts.some((h) => h.host === "together"));
  const ow = served.filter((m) => m.hosts.some((h) => h.openWeights));
  expect(ow.length).toBeGreaterThan(0);
  expect(ow.length).toBeLessThan(served.length);

  await stubCatalog(page);
  await page.goto("/providers/together");

  const rows = page.locator("table.htable tbody tr");
  await expect(rows).toHaveCount(served.length);

  // sort dropdown present with the design options
  const sort = page.locator(".f-sort select");
  await expect(sort).toBeVisible();
  expect(await sort.locator("option").allTextContents()).toEqual([
    "Newest", "Cheapest", "Intelligence", "Best value",
  ]);

  // toggle open-weights → only OW models remain; toggle off → back to all
  const owSwitch = page.locator(".f-switch");
  await expect(async () => {
    await owSwitch.click();
    await expect(owSwitch).toHaveClass(/on/, { timeout: 1_000 });
  }).toPass();
  await expect(rows).toHaveCount(ow.length);
  await owSwitch.click();
  await expect(rows).toHaveCount(served.length);
});

// ── provider page (brand hero, short name) ───────────────────────────────────

test("provider page: brand hero renders with SHORT name", async ({ page }) => {
  await stubCatalog(page);
  await page.goto("/models");

  // click the Bedrock card from the catalog grid
  const card = page.locator(".pcard", {
    has: page.locator(".pcard-name", { hasText: /^Bedrock$/ }),
  });
  await expect(async () => {
    await card.click();
    await expect(page).toHaveURL(/\/providers\/bedrock$/, { timeout: 1_000 });
  }).toPass();

  await expect(page.locator(".cp-hero-prov")).toBeVisible();
  await expect(page.locator("h1.prov-id-name")).toHaveText("Bedrock");
  await expect(page.locator("h1.prov-id-name")).not.toContainText("AWS");
});

// ── model detail ─────────────────────────────────────────────────────────────

test("model detail: ow-badge + modality chip render, back link works", async ({ page }) => {
  // an open-weights model with a plain (slash-free) id
  const m = MODELS.find(
    (x) => !x.id.includes("/") && x.hosts.some((h) => h.openWeights),
  );
  if (!m) throw new Error("fixture has no slash-free open-weights model");

  await stubCatalog(page);
  await page.goto(`/models/${m.id}`);

  await expect(page.locator("h1.model-h1")).toContainText(m.displayName);
  await expect(page.locator(".ow-badge")).toBeVisible();
  await expect(page.locator(".ow-badge")).toHaveText("Open weights");
  await expect(page.locator("h1.model-h1 .modality")).toHaveText(m.modality);

  // providers list uses SHORT host names
  const pnames = await page.locator(".pname").allTextContents();
  expect(pnames.length).toBeGreaterThan(0);
  for (const [i, h] of m.hosts.entries()) expect(pnames[i]).toBe(SHORT[h.host] ?? h.host);

  // back link "All providers" → catalog grid
  const back = page.locator(".cat-back", { hasText: "All providers" });
  await expect(async () => {
    await back.click();
    await expect(page).toHaveURL(/\/models$/, { timeout: 1_000 });
  }).toPass();
  await expect(page.locator(".cat-prov-grid")).toBeVisible();
});

// ── theme ────────────────────────────────────────────────────────────────────

test("light theme toggle flips the token set without breaking styles", async ({ page }) => {
  await page.goto("/");

  const html = page.locator("html");
  await expect(html).toHaveAttribute("data-theme", "dark");
  const darkBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);

  const toggle = page.locator(".theme-toggle").first();
  await expect(async () => {
    await toggle.click();
    await expect(html).toHaveAttribute("data-theme", "light", { timeout: 1_000 });
  }).toPass();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");

  const lightBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(lightBg).not.toBe(darkBg);
  // tokens actually resolve (no broken var() → transparent body)
  expect(lightBg).not.toBe("rgba(0, 0, 0, 0)");

  // and back to dark
  await toggle.click();
  await expect(html).toHaveAttribute("data-theme", "dark");
});
